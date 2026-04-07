"""Archival management for complete analysis sessions."""

import uuid
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from scraper.models import CompleteAnalysisSession, ScrapingSession, AggregatedBlogContent, BlogPost
from utils.logger import setup_logger

logger = setup_logger('utils.archival', 'logs/scraper.log')


class ArchivalManager:
    """Manages archiving and loading of complete analysis sessions."""
    
    def __init__(self, archive_dir: str = "archives"):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(exist_ok=True)
    
    def archive_complete_session(
        self, 
        scraping_session: ScrapingSession,
        aggregated_content: AggregatedBlogContent,
        quiz_questions: List[BlogPost],
        essay: str,
        traits: List[dict],
        analysis_metadata: dict,
        tags: List[str] = None
    ) -> str:
        """Archive a complete analysis session."""
        session_id = str(uuid.uuid4())
        analysis_session = CompleteAnalysisSession(
            session_id=session_id,
            blog_name=scraping_session.blog_name,
            username=scraping_session.username,
            scraping_session=scraping_session,
            aggregated_content=aggregated_content,
            quiz_questions=quiz_questions,
            essay=essay,
            traits=traits,
            analysis_metadata=analysis_metadata,
            created_at=datetime.now(),
            last_modified=datetime.now(),
            tags=tags or []
        )
        
        archive_path = self.archive_dir / f"{session_id}.json"
        analysis_session.save_to_file(str(archive_path))
        logger.info(f"Archived complete analysis session: {session_id}")
        return session_id
    
    def list_archived_sessions(self) -> List[dict]:
        """List all archived sessions with metadata."""
        sessions = []
        for archive_file in self.archive_dir.glob("*.json"):
            try:
                session = CompleteAnalysisSession.load_from_file(str(archive_file))
                if session:
                    sessions.append({
                        'session_id': session.session_id,
                        'blog_name': session.blog_name,
                        'username': session.username,
                        'created_at': session.created_at,
                        'last_modified': session.last_modified,
                        'tags': session.tags,
                        'post_count': session.aggregated_content.total_posts,
                        'trait_count': len(session.traits),
                        'essay_word_count': len(session.essay.split()) if session.essay else 0,
                        'quiz_question_count': len(session.quiz_questions)
                    })
            except Exception as e:
                logger.warning(f"Failed to load archive {archive_file}: {e}")
        
        sessions.sort(key=lambda x: x['created_at'], reverse=True)
        return sessions
    
    def load_archived_session(self, session_id: str) -> Optional[CompleteAnalysisSession]:
        """Load a specific archived session."""
        archive_path = self.archive_dir / f"{session_id}.json"
        session = CompleteAnalysisSession.load_from_file(str(archive_path))
        if session:
            logger.info(f"Loaded archived session: {session_id}")
        else:
            logger.warning(f"Failed to load archived session: {session_id}")
        return session
    
    def delete_archived_session(self, session_id: str) -> bool:
        """Delete an archived session."""
        archive_path = self.archive_dir / f"{session_id}.json"
        if archive_path.exists():
            archive_path.unlink()
            logger.info(f"Deleted archived session: {session_id}")
            return True
        logger.warning(f"Archived session not found for deletion: {session_id}")
        return False
    
    def get_session_summary(self, session_id: str) -> Optional[dict]:
        """Get summary information for a session without loading full data."""
        archive_path = self.archive_dir / f"{session_id}.json"
        if not archive_path.exists():
            return None
        
        try:
            import json
            with open(archive_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return {
                'session_id': data['session_id'],
                'blog_name': data['blog_name'],
                'username': data['username'],
                'created_at': data['created_at'],
                'tags': data.get('tags', []),
                'post_count': data['aggregated_content']['total_posts'],
                'trait_count': len(data['traits']),
                'essay_preview': data['essay'][:200] + "..." if len(data['essay']) > 200 else data['essay'],
                'analysis_metadata': data['analysis_metadata']
            }
        except Exception as e:
            logger.warning(f"Failed to get session summary for {session_id}: {e}")
            return None
