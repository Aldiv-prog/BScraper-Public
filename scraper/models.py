"""Data models for scraper."""

import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict


@dataclass
class BlogPost:
    """Represents a single blog post from bdsmlr.com."""
    
    post_id: str
    title: Optional[str]
    content: str
    tags: List[str]
    created_at: Optional[datetime] = None
    url: Optional[str] = None
    content_type: str = "unknown"  # "text_clear", "image_dependent", "quiz_question", "unknown"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        numeric_levels = sorted([int(t) for t in self.tags if t.isdigit() and 1 <= int(t) <= 5])
        behavior_tags = [t for t in self.tags if not (t.isdigit() and 1 <= int(t) <= 5)]

        return {
            'post_id': self.post_id,
            'title': self.title,
            'content': self.content,
            'tags': self.tags,
            'numeric_levels': numeric_levels,
            'behavior_tags': behavior_tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'url': self.url,
            'content_type': self.content_type,
        }


@dataclass
class AggregatedBlogContent:
    """Aggregated blog content ready for summarization."""
    
    total_posts: int
    raw_text: str
    tags: List[str]
    unique_tags: set
    numeric_levels: Dict[int, List[str]] = None
    behavior_tags: List[str] = None
    context_tags: List[str] = None
    trait_filter_map: Dict[str, List[str]] = None
    
    def __post_init__(self):
        self.unique_tags = set(self.tags)
        if self.numeric_levels is None:
            self.numeric_levels = {}
        if self.behavior_tags is None:
            self.behavior_tags = []
        if self.context_tags is None:
            self.context_tags = []
        if self.trait_filter_map is None:
            self.trait_filter_map = {}


@dataclass
class ScrapingSession:
    """Represents a scraping session state for resuming interrupted scraping."""
    
    blog_name: str
    username: str
    posts_scraped: List[dict]  # List of post dicts
    last_post_id: Optional[str] = None
    current_page: int = 1
    total_scroll_depth: int = 0  # How far down the page we've scrolled
    is_complete: bool = False
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'blog_name': self.blog_name,
            'username': self.username,
            'posts_scraped': self.posts_scraped,
            'last_post_id': self.last_post_id,
            'current_page': self.current_page,
            'total_scroll_depth': self.total_scroll_depth,
            'is_complete': self.is_complete,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
        }
    
    @staticmethod
    def load_from_file(filepath: str) -> Optional['ScrapingSession']:
        """Load scraping session from file."""
        path = Path(filepath)
        if not path.exists():
            return None
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            session = ScrapingSession(
                blog_name=data['blog_name'],
                username=data['username'],
                posts_scraped=data['posts_scraped'],
                last_post_id=data.get('last_post_id'),
                current_page=data.get('current_page', 1),
                total_scroll_depth=data.get('total_scroll_depth', 0),
                is_complete=data.get('is_complete', False),
                created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
                last_updated=datetime.fromisoformat(data['last_updated']) if data.get('last_updated') else None,
            )
            return session
        except Exception as e:
            print(f"Failed to load session: {e}")
            return None
    
    def save_to_file(self, filepath: str) -> None:
        """Save scraping session to file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        self.last_updated = datetime.now()
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
