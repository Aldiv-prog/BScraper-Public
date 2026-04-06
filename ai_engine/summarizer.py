"""Essay summarization engine."""

from typing import Optional
from ai_engine.ollama_client import OllamaClient
from utils.logger import setup_logger

logger = setup_logger('ai_engine.summarizer', 'logs/ai_engine.log')


class EssaySummarizer:
    """Generates personal essay from aggregated blog content."""
    
    def __init__(self, ollama_client: OllamaClient, target_words: int = 750):
        """
        Initialize essay summarizer.
        
        Args:
            ollama_client: Ollama client instance
            target_words: Target essay word count
        """
        self.ollama = ollama_client
        self.target_words = target_words
    
    def summarize(self, raw_content: str, tags: list) -> str:
        """
        Generate personal essay from blog content.
        
        Args:
            raw_content: Aggregated blog post text
            tags: List of blog tags
        
        Returns:
            Generated essay as string
        """
        tags_str = ", ".join(tags) if tags else "no tags"
        
        prompt = f"""Analyze this blog content and write a personal essay ({self.target_words} words):

BLOG CONTENT:
{raw_content}

TAGS: {tags_str}

INSTRUCTIONS:
- Write in first person as if the author is reflecting on their own worldview
- The essay should synthesize the key themes, values, and personality from the blog
- Aim for {self.target_words} words (±10% acceptable)
- Use a thoughtful, introspective tone
- Structure with clear paragraphs exploring major themes
- Do NOT include meta-commentary about the analysis

Begin the essay now:"""

        system_prompt = """You are an expert at analyzing personal blogs and synthesizing their themes into coherent personal essays. 
You understand nuance, subtext, and the deeper meaning behind expressed ideas and interests.
Write essays that are authentic, insightful, and reflect the true voice of the author."""

        logger.info(f"Generating {self.target_words}-word essay...")
        
        essay = self.ollama.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            top_p=0.9
        )
        
        word_count = len(essay.split())
        logger.info(f"Essay generated: {word_count} words")
        
        return essay
