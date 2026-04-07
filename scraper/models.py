"""Data models for scraper."""

import json
import uuid
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


@dataclass
class CompleteAnalysisSession:
    """Complete analysis session including scraping data and AI analysis results."""
    
    # Core session info
    session_id: str  # UUID for unique identification
    blog_name: str
    username: str
    
    # Scraping data
    scraping_session: ScrapingSession
    aggregated_content: AggregatedBlogContent
    quiz_questions: List[BlogPost]
    
    # Analysis results
    essay: str
    traits: List[dict]  # Trait analysis results
    analysis_metadata: dict  # Model versions, timestamps, etc.
    
    # Archival metadata
    created_at: datetime
    last_modified: datetime
    version: str = "1.0"
    tags: List[str] = None  # User-defined tags for organization
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'session_id': self.session_id,
            'blog_name': self.blog_name,
            'username': self.username,
            'scraping_session': self.scraping_session.to_dict(),
            'aggregated_content': {
                'total_posts': self.aggregated_content.total_posts,
                'raw_text': self.aggregated_content.raw_text,
                'tags': list(self.aggregated_content.tags),
                'unique_tags': list(self.aggregated_content.unique_tags)
            },
            'quiz_questions': [q.to_dict() for q in self.quiz_questions],
            'essay': self.essay,
            'traits': self.traits,
            'analysis_metadata': self.analysis_metadata,
            'created_at': self.created_at.isoformat(),
            'last_modified': self.last_modified.isoformat(),
            'version': self.version,
            'tags': self.tags
        }
    
    @staticmethod
    def load_from_file(filepath: str) -> Optional['CompleteAnalysisSession']:
        """Load complete analysis session from file."""
        path = Path(filepath)
        if not path.exists():
            return None
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Reconstruct objects from dict data
            scraping_session = ScrapingSession(
                blog_name=data['scraping_session']['blog_name'],
                username=data['scraping_session']['username'],
                posts_scraped=data['scraping_session']['posts_scraped'],
                last_post_id=data['scraping_session'].get('last_post_id'),
                current_page=data['scraping_session'].get('current_page', 1),
                total_scroll_depth=data['scraping_session'].get('total_scroll_depth', 0),
                is_complete=data['scraping_session'].get('is_complete', False),
                created_at=datetime.fromisoformat(data['scraping_session']['created_at']) if data['scraping_session'].get('created_at') else None,
                last_updated=datetime.fromisoformat(data['scraping_session']['last_updated']) if data['scraping_session'].get('last_updated') else None,
            )
            
            aggregated_content = AggregatedBlogContent(
                total_posts=data['aggregated_content']['total_posts'],
                raw_text=data['aggregated_content']['raw_text'],
                tags=data['aggregated_content']['tags'],
                unique_tags=set(data['aggregated_content']['unique_tags'])
            )
            
            quiz_questions = []
            for q_dict in data.get('quiz_questions', []):
                quiz_questions.append(BlogPost(
                    post_id=q_dict['post_id'],
                    title=q_dict.get('title'),
                    content=q_dict.get('content', ''),
                    tags=q_dict.get('tags', []),
                    created_at=datetime.fromisoformat(q_dict['created_at']) if q_dict.get('created_at') else None,
                    url=q_dict.get('url'),
                    content_type=q_dict.get('content_type', 'unknown')
                ))
            
            session = CompleteAnalysisSession(
                session_id=data['session_id'],
                blog_name=data['blog_name'],
                username=data['username'],
                scraping_session=scraping_session,
                aggregated_content=aggregated_content,
                quiz_questions=quiz_questions,
                essay=data['essay'],
                traits=data['traits'],
                analysis_metadata=data['analysis_metadata'],
                created_at=datetime.fromisoformat(data['created_at']),
                last_modified=datetime.fromisoformat(data['last_modified']),
                version=data.get('version', '1.0'),
                tags=data.get('tags', [])
            )
            return session
        except Exception as e:
            print(f"Failed to load complete analysis session: {e}")
            return None
    
    def save_to_file(self, filepath: str) -> None:
        """Save complete analysis session to file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        self.last_modified = datetime.now()
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
