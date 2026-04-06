"""Content aggregation utilities."""

import json
from pathlib import Path
from typing import List, Tuple, Dict
from scraper.models import BlogPost, AggregatedBlogContent
from utils.logger import setup_logger

logger = setup_logger('processor.aggregator', 'logs/scraper.log')


class ContentAggregator:
    """Aggregates multiple blog posts into a single content block."""
    
    @staticmethod
    def aggregate(posts: List[BlogPost]) -> Tuple[AggregatedBlogContent, List[BlogPost]]:
        """
        Aggregate multiple posts into single content block, filtering by content type.
        
        Args:
            posts: List of blog posts
        
        Returns:
            Tuple of (AggregatedBlogContent for trait inference, quiz questions)
        """
        if not posts:
            logger.warning("No posts to aggregate")
            empty_content = AggregatedBlogContent(
                total_posts=0,
                raw_text="",
                tags=[],
                unique_tags=set()
            )
            return empty_content, []
        
        # Separate posts by content type
        text_clear_posts = []
        quiz_questions = []
        skipped_posts = []
        
        for post in posts:
            if post.content_type == "text_clear":
                text_clear_posts.append(post)
            elif post.content_type == "quiz_question":
                quiz_questions.append(post)
            else:
                skipped_posts.append(post)
        
        logger.info(
            f"Content filtering: {len(text_clear_posts)} text_clear, "
            f"{len(quiz_questions)} quiz_questions, {len(skipped_posts)} skipped"
        )
        
        # Save quiz questions for later reference
        if quiz_questions:
            ContentAggregator._save_quiz_questions(quiz_questions)
        
        # Only aggregate text_clear posts for trait inference, fallback to quiz_questions
        posts_for_aggregation = text_clear_posts if text_clear_posts else quiz_questions
        
        if not posts_for_aggregation:
            logger.warning("No suitable posts found for trait inference")
            empty_content = AggregatedBlogContent(
                total_posts=0,
                raw_text="",
                tags=[],
                unique_tags=set()
            )
            return empty_content, quiz_questions
        
        # Combine posts with advanced tag structure
        text_parts = []
        all_tags = []
        level_tag_mapping: Dict[int, List[str]] = {1: [], 2: [], 3: [], 4: [], 5: []}
        behavior_tags = []
        context_tags = []

        for post in posts_for_aggregation:
            if post.title:
                text_parts.append(f"## {post.title}\n")

            text_parts.append(post.content)
            text_parts.append("\n")

            for tag in post.tags:
                normalized_tag = tag.strip().lower()
                if normalized_tag.isdigit() and 1 <= int(normalized_tag) <= 5:
                    level_tag_mapping[int(normalized_tag)].append(post.post_id)
                elif normalized_tag in ('quiz', 'text_clear', 'image_dependent'):
                    continue  # classification tags are not behavior/context tags
                elif normalized_tag in ('home', 'work', 'public', 'private', 'bedroom', 'outdoors'):
                    context_tags.append(normalized_tag)
                else:
                    behavior_tags.append(normalized_tag)

            all_tags.extend(post.tags)

        raw_text = "\n".join(text_parts)
        
        logger.info(
            f"Aggregated {len(posts_for_aggregation)} posts | "
            f"{len(raw_text)} characters | {len(set(all_tags))} unique tags"
        )
        
        # Build trait filter map from tags (for quiz and trait-based evaluation)
        trait_filter_map = {}
        for tag in set(all_tags):
            normalized_tag = tag.strip().lower()

            if normalized_tag.isdigit() and 1 <= int(normalized_tag) <= 5:
                trait_filter_map[normalized_tag] = ['difficulty_level']
            elif normalized_tag in ('dominance', 'submission', 'obedience', 'service', 'respect'):
                trait_filter_map[normalized_tag] = ['authority', 'compliance']
            elif normalized_tag in ('outfit', 'dress', 'clothes'):
                trait_filter_map[normalized_tag] = ['presentation', 'aesthetic']
            elif normalized_tag in ('attitude', 'mindset', 'behavior', 'role'):
                trait_filter_map[normalized_tag] = ['psychology', 'discipline']
            else:
                trait_filter_map[normalized_tag] = ['general']

        aggregated = AggregatedBlogContent(
            total_posts=len(posts_for_aggregation),
            raw_text=raw_text,
            tags=all_tags,
            unique_tags=set(all_tags),
            numeric_levels={k: list(set(v)) for k, v in level_tag_mapping.items() if v},
            behavior_tags=list(set(behavior_tags)),
            context_tags=list(set(context_tags)),
            trait_filter_map=trait_filter_map
        )

        return aggregated, quiz_questions
    
    @staticmethod
    def _save_quiz_questions(quiz_posts: List[BlogPost]) -> None:
        """
        Save quiz questions to a separate file for later reference.
        
        Args:
            quiz_posts: Posts tagged as quiz questions
        """
        if not quiz_posts:
            return
        
        # Create output directory if it doesn't exist
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        quiz_data = {
            "quiz_questions": [post.to_dict() for post in quiz_posts],
            "total_questions": len(quiz_posts),
            "saved_at": "2026-03-25T06:13:33.312055"  # Current timestamp
        }
        
        quiz_file = output_dir / "quiz_questions.json"
        with open(quiz_file, 'w', encoding='utf-8') as f:
            json.dump(quiz_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(quiz_posts)} quiz questions to {quiz_file}")
