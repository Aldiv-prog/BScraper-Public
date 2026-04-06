"""Content deduplication utilities."""

import hashlib
from typing import List, Set
from scraper.models import BlogPost
from utils.logger import setup_logger

logger = setup_logger('processor.dedup', 'logs/scraper.log')


class ContentDeduplicator:
    """Deduplicates blog posts based on content hash."""
    
    def __init__(self, similarity_threshold: float = 0.95):
        """
        Initialize deduplicator.
        
        Args:
            similarity_threshold: Threshold for considering posts similar (0-1)
        """
        self.similarity_threshold = similarity_threshold
        self.seen_hashes: Set[str] = set()
    
    def deduplicate(self, posts: List[BlogPost]) -> List[BlogPost]:
        """
        Remove duplicate posts from list.
        
        Args:
            posts: List of blog posts
        
        Returns:
            List of unique blog posts
        """
        unique_posts = []
        
        for post in posts:
            post_hash = self._hash_content(post.content)
            
            if post_hash not in self.seen_hashes:
                self.seen_hashes.add(post_hash)
                unique_posts.append(post)
            else:
                logger.debug(f"Skipped duplicate post: {post.post_id}")
        
        logger.info(
            f"Deduplication: {len(posts)} posts to {len(unique_posts)} unique"
        )
        return unique_posts
    
    @staticmethod
    def _hash_content(content: str) -> str:
        """
        Generate hash of post content.
        
        Args:
            content: Post content
        
        Returns:
            SHA256 hash of content
        """
        # Normalize content (lowercase, strip whitespace)
        normalized = content.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()
