"""BScraper main entry point."""

import getpass
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional
from collections import Counter

from utils.config_loader import ConfigLoader
from utils.logger import setup_logger
from utils.exceptions import BScrapeException
from utils.archival_manager import ArchivalManager

from scraper.models import BlogPost, ScrapingSession, CompleteAnalysisSession, AggregatedBlogContent
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


def _prompt_menu_choice(options: list, prompt: str = 'Enter your choice') -> str:
    """Print a numbered menu and return a valid user choice."""
    while True:
        print()
        for option in options:
            print(option)
        print()
        choice = input(f"{prompt} ({1}-{len(options)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return choice
        print("Invalid choice. Please enter a valid number.")


def _backup_scraping_session(session_file: str, backup_root: str = 'archives/session_backups') -> str:
    """Backup the current scraping session to a timestamped JSON file."""
    source = Path(session_file)
    if not source.exists():
        raise BScrapeException(f"Session file not found: {session_file}")

    backup_dir = Path(backup_root)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f"{source.stem}_{timestamp}.json"
    backup_path.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')

    return str(backup_path)


def _load_session_backup_workflow(backup_root: str = 'archives/session_backups') -> Optional[Tuple[List[BlogPost], ScrapingSession]]:
    """Interactive workflow to load a backed-up scraping session."""
    backup_dir = Path(backup_root)
    if not backup_dir.exists():
        print("No session backups found.")
        return None
        
    backups = sorted(backup_dir.glob('*.json'), reverse=True)

    if not backups:
        print("No session backups found.")
        return None

    print("\n" + "=" * 60)
    print("LOAD SCRAPED SESSION BACKUP")
    print("=" * 60)

    for i, backup in enumerate(backups, 1):
        mod_time = datetime.fromtimestamp(backup.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{i}. {backup.name} ({mod_time})")
    print("c. Cancel")

    while True:
        choice = input(f"Select a session to load (1-{len(backups)}) or 'c' to cancel: ").strip()
        if choice.lower() == 'c':
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(backups):
            selected_file = backups[int(choice) - 1]
            session = ScrapingSession.load_from_file(str(selected_file))
            if not session:
                print(f"Failed to load backup: {selected_file}")
                return None
            return _posts_from_session(session), session

        print("Invalid selection. Please enter a valid number or 'c'.")


def _inspect_scraped_data(posts: List[BlogPost], session: ScrapingSession) -> None:
    """Display detailed information about scraped data for inspection."""
    print("\n" + "=" * 60)
    print("SCRAPED DATA INSPECTION")
    print("=" * 60)

    print(f"Blog: {session.blog_name}")
    print(f"Username: {session.username}")
    print(f"Total posts scraped: {len(posts)}")
    print(f"Session created: {session.created_at}")
    print(f"Last updated: {session.last_updated}")
    print(f"Current page: {session.current_page}")
    print(f"Scroll depth: {session.total_scroll_depth}")
    print(f"Session complete: {session.is_complete}")
    print()

    text_clear = sum(1 for p in posts if p.content_type == 'text_clear')
    image_dependent = sum(1 for p in posts if p.content_type == 'image_dependent')
    quiz_questions = sum(1 for p in posts if p.content_type == 'quiz_question')
    unknown = sum(1 for p in posts if p.content_type == 'unknown')

    print("Content type breakdown:")
    print(f"  Text posts: {text_clear}")
    print(f"  Image-dependent: {image_dependent}")
    print(f"  Quiz questions: {quiz_questions}")
    print(f"  Unknown: {unknown}")
    print()

    all_tags = []
    for post in posts:
        all_tags.extend(post.tags)

    unique_tags = set(all_tags)
    print(f"Total tags found: {len(all_tags)}")
    print(f"Unique tags: {len(unique_tags)}")
    print()

    if unique_tags:
        print("Top 10 tags by frequency:")
        tag_counts = Counter(all_tags)
        for tag, count in tag_counts.most_common(10):
            print(f"  #{tag}: {count}")
        print()

    if posts:
        print("Recent posts sample:")
        recent_posts = sorted(posts, key=lambda p: p.created_at or datetime.min, reverse=True)[:3]
        for i, post in enumerate(recent_posts, 1):
            created = post.created_at.strftime("%Y-%m-%d") if post.created_at else "Unknown"
            content_preview = post.content[:100] + "..." if len(post.content) > 100 else post.content
            print(f"  {i}. [{created}] {content_preview}")
        print()

    input("Press Enter to continue...")


def _archive_session_workflow(
    scraping_session: ScrapingSession,
    aggregated_content: AggregatedBlogContent,
    quiz_questions: List[BlogPost],
    essay: str,
    traits: List[dict],
    analysis_metadata: dict,
    config: ConfigLoader
) -> None:
    """Interactive workflow for archiving complete analysis results."""
    
    print("\n" + "=" * 60)
    print("SESSION ARCHIVING")
    print("=" * 60)
    
    archival_manager = ArchivalManager()
    
    try:
        tags_input = input("Enter tags for this analysis (comma-separated, optional): ").strip()
        tags = [tag.strip() for tag in tags_input.split(',')] if tags_input else []
    except EOFError:
        tags = []
        print("No tags provided (running non-interactively)")
    
    session_id = archival_manager.archive_complete_session(
        scraping_session, aggregated_content, quiz_questions, essay, traits, analysis_metadata, tags
    )
    
    print(f"Analysis archived successfully!")
    print(f"Session ID: {session_id}")
    print(f"Archive location: archives/{session_id}.json")
    print(f"Tags: {', '.join(tags) if tags else 'None'}")
    
    try:
        input("Press Enter to continue...")
    except EOFError:
        print("Archiving complete.")


def _load_archived_session_workflow(config: ConfigLoader) -> Optional[CompleteAnalysisSession]:
    """Interactive workflow for loading archived sessions."""
    
    archival_manager = ArchivalManager()
    archived_sessions = archival_manager.list_archived_sessions()
    
    if not archived_sessions:
        print("No archived sessions found.")
        return None
    
    print("\n" + "=" * 60)
    print("LOAD ARCHIVED SESSION")
    print("=" * 60)
    print("Available archived sessions:")
    print()
    
    for i, session in enumerate(archived_sessions, 1):
        created = session['created_at'].strftime("%Y-%m-%d %H:%M")
        tags_str = f" [{', '.join(session['tags'])}]" if session['tags'] else ""
        print(f"{i}. {session['blog_name']} - {session['username']}")
        print(f"   {created} | {session['post_count']} posts | {session['trait_count']} traits{tags_str}")
        print()
    
    while True:
        choice = input(f"Select session to load (1-{len(archived_sessions)}) or 'c' to cancel: ").strip()
        
        if choice.lower() == 'c':
            return None
        
        try:
            index = int(choice) - 1
            if 0 <= index < len(archived_sessions):
                session_id = archived_sessions[index]['session_id']
                return archival_manager.load_archived_session(session_id)
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a number or 'c' to cancel.")


def _display_archived_session_details(session: CompleteAnalysisSession) -> None:
    """Display detailed information about an archived analysis session."""
    
    print("\n" + "=" * 60)
    print("ARCHIVED SESSION DETAILS")
    print("=" * 60)
    
    print(f"Session ID: {session.session_id}")
    print(f"Blog: {session.blog_name}")
    print(f"Username: {session.username}")
    print(f"Created: {session.created_at}")
    print(f"Last Modified: {session.last_modified}")
    print(f"Version: {session.version}")
    print(f"Tags: {', '.join(session.tags) if session.tags else 'None'}")
    print()
    
    print("CONTENT SUMMARY:")
    print(f"  Posts analyzed: {session.aggregated_content.total_posts}")
    print(f"  Unique tags: {len(session.aggregated_content.unique_tags)}")
    print(f"  Quiz questions: {len(session.quiz_questions)}")
    print()
    
    print("ANALYSIS RESULTS:")
    print(f"  Personality traits identified: {len(session.traits)}")
    print(f"  Essay word count: {len(session.essay.split()) if session.essay else 0}")
    print()
    
    print("ANALYSIS METADATA:")
    for key, value in session.analysis_metadata.items():
        print(f"  {key}: {value}")
    print()
    
    print("ESSAY PREVIEW:")
    essay_preview = session.essay[:300] + "..." if len(session.essay) > 300 else session.essay
    print(f"  {essay_preview}")
    print()
    
    if session.traits:
        print("TOP TRAITS:")
        for i, trait in enumerate(session.traits[:5], 1):
            confidence = trait.get('confidence', 0)
            name = trait.get('name', 'Unknown')
            print(f"  {i}. {name} ({confidence}%)")
        if len(session.traits) > 5:
            print(f"  ... and {len(session.traits) - 5} more")
        print()
    
    input("Press Enter to continue...")


def _interactive_post_scraping_workflow(
    posts: List[BlogPost],
    scraping_session: ScrapingSession,
    config: ConfigLoader,
    session_file: str,
    args
) -> str:
    """Interactive workflow after scraping completes."""
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Scraped {len(posts)} posts from {scraping_session.blog_name}")
    print(f"Session saved to: {session_file}")
    print()

    menu_options = [
        "1. Continue with analysis (summarize + traits)",
        "2. Generate essay only (summarization phase)",
        "3. Extract traits only (trait inference phase)",
        "4. Inspect scraped data (view session details)",
        "5. Quit (exit without further analysis)"
    ]

    choice = _prompt_menu_choice(menu_options)
    if choice == '1':
        return 'all'
    elif choice == '2':
        return 'summarize'
    elif choice == '3':
        return 'traits'
    elif choice == '4':
        _inspect_scraped_data(posts, scraping_session)
        return _interactive_post_scraping_workflow(posts, scraping_session, config, session_file, args)
    elif choice == '5':
        return 'quit'


def _handle_existing_session_workflow(
    session_file: str,
    config: ConfigLoader,
    args
) -> Tuple[List[BlogPost], ScrapingSession, str]:
    """Handle workflow when existing session data is found."""
    saved_session = ScrapingSession.load_from_file(session_file)

    if not saved_session:
        return [], None, 'scrape'

    print("\n" + "=" * 60)
    print("EXISTING SESSION FOUND")
    print("=" * 60)
    print(f"Session file: {session_file}")
    print(f"Posts saved: {len(saved_session.posts_scraped)}")
    print(f"Blog: {saved_session.blog_name}")
    print(f"Username: {saved_session.username}")
    print(f"Created: {saved_session.created_at}")
    print(f"Complete: {saved_session.is_complete}")
    print()

    if saved_session.is_complete:
        menu_options = [
            "1. Re-analyze existing data (skip scraping)",
            "2. Start fresh scraping (overwrite session)",
            "3. Resume incomplete scraping (if marked incomplete)",
            "4. Save current session to a session archive",
            "5. Load a saved session archive",
            "6. Inspect session data",
            "7. Quit"
        ]

        choice = _prompt_menu_choice(menu_options)
        if choice == '1':
            posts, session = _load_scraping_session(session_file)
            return posts, session, 'all'
        elif choice == '2':
            return [], None, 'scrape'
        elif choice == '3':
            posts, session = _load_scraping_session(session_file)
            return posts, session, 'resume_scraping'
        elif choice == '4':
            backup_path = _backup_scraping_session(session_file)
            print(f"Saved session archive to: {backup_path}")
            return _handle_existing_session_workflow(session_file, config, args)
        elif choice == '5':
            loaded = _load_session_backup_workflow()
            if loaded:
                return loaded[0], loaded[1], 'all'
            return _handle_existing_session_workflow(session_file, config, args)
        elif choice == '6':
            posts, session = _load_scraping_session(session_file)
            _inspect_scraped_data(posts, session)
            return _handle_existing_session_workflow(session_file, config, args)
        elif choice == '7':
            return [], None, 'quit'
    else:
        menu_options = [
            "1. Resume scraping from where it left off",
            "2. Re-analyze existing data only (skip further scraping)",
            "3. Start fresh scraping (overwrite session)",
            "4. Save current session to a session archive",
            "5. Load a saved session archive",
            "6. Inspect current session data",
            "7. Quit"
        ]

        choice = _prompt_menu_choice(menu_options)
        if choice == '1':
            posts, session = _load_scraping_session(session_file)
            return posts, session, 'resume_scraping'
        elif choice == '2':
            posts, session = _load_scraping_session(session_file)
            return posts, session, 'all'
        elif choice == '3':
            return [], None, 'scrape'
        elif choice == '4':
            backup_path = _backup_scraping_session(session_file)
            print(f"Saved session archive to: {backup_path}")
            return _handle_existing_session_workflow(session_file, config, args)
        elif choice == '5':
            loaded = _load_session_backup_workflow()
            if loaded:
                return loaded[0], loaded[1], 'all'
            return _handle_existing_session_workflow(session_file, config, args)
        elif choice == '6':
            posts, session = _load_scraping_session(session_file)
            _inspect_scraped_data(posts, session)
            return _handle_existing_session_workflow(session_file, config, args)
        elif choice == '7':
            return [], None, 'quit'


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
    parser.add_argument('--force-resume', action='store_true',
                        help='Force resume scraping even if session appears complete')
    parser.add_argument('--archive', action='store_true',
                        help='Archive complete analysis results after processing')
    parser.add_argument('--load-archive', action='store_true',
                        help='Load and view archived analysis sessions')
    parser.add_argument('--list-archives', action='store_true',
                        help='List all archived analysis sessions')
    parser.add_argument('--save-session-backup', action='store_true',
                        help='Save the current scraping session to a timestamped backup archive')
    parser.add_argument('--list-session-backups', action='store_true',
                        help='List all saved scraping session backups')
    parser.add_argument('--load-session-backup', action='store_true',
                        help='Load a saved scraping session backup interactively')
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

        # Handle archival CLI commands first
        if args.list_archives:
            archival_manager = ArchivalManager()
            archived_sessions = archival_manager.list_archived_sessions()
            
            if not archived_sessions:
                print("No archived sessions found.")
                return 0
            
            print("\n" + "=" * 80)
            print("ARCHIVED ANALYSIS SESSIONS")
            print("=" * 80)
            
            for i, session in enumerate(archived_sessions, 1):
                created = session['created_at'].strftime("%Y-%m-%d %H:%M")
                tags_str = f" [{', '.join(session['tags'])}]" if session['tags'] else ""
                print(f"{i:2d}. {session['blog_name']:<20} | {session['username']:<15} | {created} | {session['post_count']:3d} posts | {session['trait_count']:2d} traits{tags_str}")
            
            print(f"\nTotal: {len(archived_sessions)} archived sessions")
            return 0
        
        elif args.list_session_backups:
            backup_dir = Path('archives/session_backups')
            backups = sorted(backup_dir.glob('*.json'), reverse=True) if backup_dir.exists() else []
            if not backups:
                print("No session backups found.")
                return 0
            
            print("\n" + "=" * 80)
            print("SESSION BACKUP ARCHIVES")
            print("=" * 80)
            for i, backup in enumerate(backups, 1):
                created = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                print(f"{i:2d}. {backup.name:<40} | {created}")
            print(f"\nTotal: {len(backups)} session backups")
            return 0
        
        elif args.save_session_backup:
            backup_path = _backup_scraping_session(session_file)
            print(f"Saved session archive to: {backup_path}")
            return 0
        
        elif args.load_archive:
            archived_session = _load_archived_session_workflow(config)
            if archived_session:
                _display_archived_session_details(archived_session)
            return 0
        
        elif args.load_session_backup:
            loaded = _load_session_backup_workflow()
            if loaded:
                posts, scraping_session = loaded
                print(f"Loaded backup session from archive. {len(posts)} posts available.")
            return 0

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
