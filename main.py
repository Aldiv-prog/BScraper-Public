"""BScraper main entry point."""

import getpass
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional

from utils.config_loader import ConfigLoader
from utils.logger import setup_logger
from utils.exceptions import BScrapeException

from scraper.models import BlogPost, ScrapingSession
from scraper.session_manager import SessionManager
from scraper.bdsmlr_scraper import BdsmlrScraper

from processor.deduplicator import ContentDeduplicator
from processor.aggregator import ContentAggregator

from ai_engine.ollama_client import OllamaClient
from ai_engine.summarizer import EssaySummarizer
from ai_engine.trait_extractor import PersonalityTraitExtractor

logger = setup_logger('main', 'logs/scraper.log')


def _posts_from_session(session: ScrapingSession) -> List[BlogPost]:
    """Convert saved session post dictionaries into BlogPost objects."""
    return [
        BlogPost(
            post_id=p['post_id'],
            title=p.get('title'),
            content=p.get('content', ''),
            tags=p.get('tags', []),
            created_at=datetime.fromisoformat(p['created_at']) if p.get('created_at') else None,
            url=p.get('url'),
            content_type=p.get('content_type', 'unknown')
        )
        for p in session.posts_scraped
    ]


def _load_scraping_session(session_file: str) -> Tuple[List[BlogPost], ScrapingSession]:
    """Load scraping session data from disk for analysis phases."""
    session = ScrapingSession.load_from_file(session_file)
    if not session:
        raise BScrapeException(f"No saved scraping session found at {session_file}")

    return _posts_from_session(session), session


def main():
    """Main pipeline: Scrape → Summarize → Extract Traits."""
    
    parser = argparse.ArgumentParser(description='BScraper: Blog Analysis Pipeline')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--config', default='config.yaml', help='Path to config file')
    parser.add_argument('--phase', choices=['all', 'scrape', 'summarize', 'traits'], default='all',
                        help='Pipeline phase to run')
    parser.add_argument('--resume', action='store_true',
                        help='Automatically resume a saved scraping session without prompts')
    parser.add_argument('--session-file', default='output/scraping_session.json',
                        help='Path to saved scraping session file')
    parser.add_argument('--max-pages', type=int, help='Maximum pages to scrape')
    args = parser.parse_args()
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = ConfigLoader(args.config)
        
        # Set logging level based on verbose flag
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            for name in ['main', 'scraper.session', 'scraper.bdsmlr', 'processor', 'ai_engine']:
                log = logging.getLogger(name)
                log.setLevel(logging.DEBUG)
                for handler in log.handlers:
                    handler.setLevel(logging.DEBUG)
        
        scraper_config = config.get_scraper_config()
        summarizer_config = config.get_summarizer_config()
        traits_config = config.get_traits_config()
        output_config = config.get_output_config()
        
        session_file = args.session_file
        blog_name = scraper_config.get('blog_name')
        if not blog_name:
            raise BScrapeException("blog_name not configured in config.yaml")

        posts: List[BlogPost] = []
        scraping_session: Optional[ScrapingSession] = None
        session_manager: Optional[SessionManager] = None

        if args.phase in ('all', 'scrape'):
            # PHASE 1: Scraping is required for both full pipeline and scrape-only mode
            logger.info("Prompting for credentials...")
            username = input("Enter bdsmlr.com username: ")
            logger.info("Username received")
            password = getpass.getpass("Enter bdsmlr.com password: ")
            logger.info("Password input received")

            logger.info("=" * 60)
            logger.info("PHASE 1: SCRAPING")
            logger.info("=" * 60)

            proxy_config = scraper_config.get('proxy', {})
            proxy_url = proxy_config.get('url') if proxy_config.get('enabled') else None

            session_manager = SessionManager(
                base_url=scraper_config.get('base_url', 'https://bdsmlr.com'),
                proxy_url=proxy_url,
                request_delay=scraper_config.get('request_delay', 2),
                timeout=scraper_config.get('timeout', 10),
                verify_ssl=scraper_config.get('verify_ssl', True)
            )

            logger.info(f"Authenticating as {username}...")
            if not session_manager.authenticate(username, password):
                raise BScrapeException("Authentication failed")

            scraper = BdsmlrScraper(session_manager, session_file=session_file)
            posts, scraping_session = scraper.scrape_blog_interactive(
                blog_name,
                username,
                auto_resume=args.resume
            )
            logger.info(f"Scraped {len(posts)} posts from {blog_name}")

            if args.phase == 'scrape':
                logger.info("Scrape-only phase complete")
                return 0

        elif args.phase == 'summarize':
            saved_session = ScrapingSession.load_from_file(session_file)
            if args.resume and saved_session and not saved_session.is_complete:
                logger.info("Resuming unfinished scraping session before summarization")
                logger.info("Prompting for credentials...")
                username = input("Enter bdsmlr.com username: ")
                logger.info("Username received")
                password = getpass.getpass("Enter bdsmlr.com password: ")
                logger.info("Password input received")

                proxy_config = scraper_config.get('proxy', {})
                proxy_url = proxy_config.get('url') if proxy_config.get('enabled') else None
                session_manager = SessionManager(
                    base_url=scraper_config.get('base_url', 'https://bdsmlr.com'),
                    proxy_url=proxy_url,
                    request_delay=scraper_config.get('request_delay', 2),
                    timeout=scraper_config.get('timeout', 10),
                    verify_ssl=scraper_config.get('verify_ssl', True)
                )
                logger.info(f"Authenticating as {username}...")
                if not session_manager.authenticate(username, password):
                    raise BScrapeException("Authentication failed")

                scraper = BdsmlrScraper(session_manager, session_file=session_file)
                posts, scraping_session = scraper.scrape_blog_interactive(
                    blog_name,
                    username,
                    auto_resume=True
                )
                logger.info(f"Resumed scraping and collected {len(posts)} posts")
            else:
                posts, scraping_session = _load_scraping_session(session_file)
                logger.info(f"Loaded saved scraping session with {len(posts)} posts")

        elif args.phase == 'traits':
            logger.info("=" * 60)
            logger.info("PHASE 3: TRAIT EXTRACTION")
            logger.info("=" * 60)
            
            confidence_threshold = output_config.get('traits_confidence_threshold', 50)
            
            # Initialize Ollama for trait generation
            ollama_client = OllamaClient(
                base_url=summarizer_config.get('ollama_url', 'http://localhost:11434'),
                model=summarizer_config.get('ollama_model', 'gemma-3-4b-it-uncensored-v2-gguf:q5_k_m'),
                timeout=summarizer_config.get('timeout', 120)
            )
            logger.info("Checking Ollama connection...")
            ollama_client.check_connection()
            
            # Load raw content from scraping session to extract traits
            posts, scraping_session = _load_scraping_session(session_file)
            deduplicator = ContentDeduplicator()
            unique_posts = deduplicator.deduplicate(posts)
            aggregator = ContentAggregator()
            aggregated, _ = aggregator.aggregate(unique_posts)
            
            logger.info(f"Loaded {len(posts)} posts from session for trait extraction")
            
            # Initialize trait extractor with comprehensive parsing
            trait_extractor = PersonalityTraitExtractor(
                ollama_client=ollama_client,
                base_traits=traits_config.get('base_traits', []),
                custom_traits=traits_config.get('custom_traits', []),
                confidence_threshold=confidence_threshold
            )
            
            # Generate traits from raw blog content and write to raw log file
            trait_extractor.generate_traits_from_content(
                raw_content=aggregated.raw_text,
                tags=list(aggregated.unique_tags)
            )
            
            # Extract traits from the raw log file
            traits = trait_extractor.extract_traits()
            
            logger.info(f"Successfully extracted {len(traits)} traits from raw blog content")
            traits_output = {
                'traits': traits,
                'summary_reference': 'logs/ai_engine_trait_response_raw.txt',
                'generated_at': datetime.now().isoformat(),
                'total_identified': len(traits),
                'expected_total': traits_config.get('total_count', 20)
            }
            traits_path = Path(output_config.get('traits_file', 'output/traits.json'))
            traits_path.parent.mkdir(parents=True, exist_ok=True)
            traits_path.write_text(json.dumps(traits_output, indent=2, ensure_ascii=False))
            logger.info(f"Traits saved to {traits_path}")
            logger.info("=" * 60)
            logger.info("TRAIT EXTRACTION COMPLETE")
            logger.info("=" * 60)
            return 0

        # Deduplicate
        deduplicator = ContentDeduplicator()
        unique_posts = deduplicator.deduplicate(posts)
        
        # Aggregate
        aggregator = ContentAggregator()
        aggregated, quiz_questions = aggregator.aggregate(unique_posts)
        
        logger.info(f"Raw content: {len(aggregated.raw_text)} characters")
        logger.info(f"Unique tags: {len(aggregated.unique_tags)}")
        logger.info(f"Quiz questions saved: {len(quiz_questions)}")
        
        # ==================== PHASE 2: SUMMARIZATION ====================
        logger.info("=" * 60)
        logger.info("PHASE 2: SUMMARIZATION")
        logger.info("=" * 60)
        
        # Initialize Ollama
        ollama_client = OllamaClient(
            base_url=summarizer_config.get('ollama_url', 'http://localhost:11434'),
            model=summarizer_config.get('ollama_model', 'gemma-3-4b-it-uncensored-v2-gguf:q5_k_m'),
            timeout=summarizer_config.get('timeout', 120)
        )
        
        logger.info("Checking Ollama connection...")
        ollama_client.check_connection()
        
        # Generate essay
        summarizer = EssaySummarizer(
            ollama_client=ollama_client,
            target_words=output_config.get('essay_word_count', 750)
        )
        
        essay = summarizer.summarize(aggregated.raw_text, list(aggregated.unique_tags))
        
        # Save essay
        essay_path = Path(output_config.get('essay_file', 'output/essay.txt'))
        essay_path.parent.mkdir(parents=True, exist_ok=True)
        essay_path.write_text(essay)
        logger.info(f"Essay saved to {essay_path}")
        
        # ==================== PHASE 3: TRAIT EXTRACTION ====================
        logger.info("=" * 60)
        logger.info("PHASE 3: TRAIT EXTRACTION")
        logger.info("=" * 60)
        
        confidence_threshold = output_config.get('traits_confidence_threshold', 50)
        
        # Initialize trait extractor with comprehensive parsing
        trait_extractor = PersonalityTraitExtractor(
            ollama_client=ollama_client,
            base_traits=traits_config.get('base_traits', []),
            custom_traits=traits_config.get('custom_traits', []),
            confidence_threshold=confidence_threshold
        )
        
        # Generate traits from raw blog content and write to raw log file
        trait_extractor.generate_traits_from_content(
            raw_content=aggregated.raw_text,
            tags=list(aggregated.unique_tags)
        )
        
        # Extract traits from the raw log file
        traits = trait_extractor.extract_traits()
        
        # Prepare traits output
        traits_output = {
            'traits': traits,
            'summary_reference': 'logs/ai_engine_trait_response_raw.txt',
            'generated_at': datetime.now().isoformat(),
            'total_identified': len(traits),
            'expected_total': traits_config.get('total_count', 20)
        }
        
        # Save traits
        traits_path = Path(output_config.get('traits_file', 'output/traits.json'))
        traits_path.parent.mkdir(parents=True, exist_ok=True)
        traits_path.write_text(json.dumps(traits_output, indent=2, ensure_ascii=False))
        logger.info(f"Traits saved to {traits_path}")
        
        # ==================== SUMMARY ====================
        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Scraped {len(unique_posts)} unique posts")
        logger.info(f"Generated {output_config.get('essay_word_count', 750)}-word essay")
        logger.info(f"Identified {len(traits)} personality traits")
        logger.info(f"\nOutput files:")
        logger.info(f"  - Essay: {essay_path}")
        logger.info(f"  - Traits: {traits_path}")
        
        if session_manager:
            session_manager.close()
        
    except BScrapeException as e:
        logger.error(f"Pipeline error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
