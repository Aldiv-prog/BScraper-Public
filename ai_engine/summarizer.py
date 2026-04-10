"""Essay summarization engine — chunked map-reduce for large blogs."""

from typing import Optional
from ai_engine.ollama_client import OllamaClient
from utils.logger import setup_logger

logger = setup_logger('ai_engine.summarizer', 'logs/ai_engine.log')


# ---------------------------------------------------------------------------
# Chunking helper (post-boundary aware)
# ---------------------------------------------------------------------------

def chunk_posts(posts: list, max_context_chars: int) -> list[list]:
    """Split a list of BlogPost objects into chunks that stay within
    max_context_chars, always splitting at post boundaries.

    Args:
        posts: List of BlogPost objects (must have a .text attribute).
        max_context_chars: Maximum total character count per chunk.

    Returns:
        List of chunks, each chunk being a list of BlogPost objects.
    """
    chunks: list[list] = []
    current_chunk: list = []
    current_chars: int = 0

    for post in posts:
        post_text = getattr(post, 'text', '') or ''
        post_len = len(post_text)

        # If a single post exceeds the cap on its own, put it in its own chunk.
        if post_len >= max_context_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
            chunks.append([post])
            logger.warning(
                f"Post index {len(chunks) - 1} exceeds max_context_chars "
                f"({post_len} chars); placed in its own chunk."
            )
            continue

        # Adding this post would exceed the cap — start a new chunk.
        if current_chars + post_len > max_context_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_chars = 0

        current_chunk.append(post)
        current_chars += post_len

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# ---------------------------------------------------------------------------
# EssaySummarizer
# ---------------------------------------------------------------------------

class EssaySummarizer:
    """Generates a personal essay from aggregated blog content.

    For blogs whose total text exceeds *max_context_chars*, a map-reduce
    approach is used:
      MAP   — each chunk is summarised independently into a partial essay.
      REDUCE — all partial essays are combined in a second Ollama pass.

    For small blogs the original single-pass path is used unchanged.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        target_words: int = 750,
        max_context_chars: int = 40_000,
    ):
        """
        Args:
            ollama_client: Configured OllamaClient instance.
            target_words: Target word count for the final essay.
            max_context_chars: Character cap per chunk (default 40 000).
        """
        self.ollama = ollama_client
        self.target_words = target_words
        self.max_context_chars = max_context_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize(self, raw_content: str, tags: list, posts: list = None) -> str:
        """Generate a personal essay from blog content.

        Args:
            raw_content: Aggregated blog text (used for single-pass path).
            tags: List of blog tags.
            posts: Optional list of BlogPost objects for chunked path.
                   When provided and total chars exceed max_context_chars,
                   the map-reduce path is taken.

        Returns:
            Generated essay as a single string.
        """
        tags_str = ", ".join(tags) if tags else "no tags"

        # Decide: single-pass or map-reduce?
        if posts and len(raw_content) > self.max_context_chars:
            return self._map_reduce(posts, tags_str)
        else:
            return self._single_pass(raw_content, tags_str)

    # ------------------------------------------------------------------
    # Single-pass path (unchanged from original)
    # ------------------------------------------------------------------

    def _single_pass(self, raw_content: str, tags_str: str) -> str:
        """Original single-Ollama-call summarization."""
        prompt = self._build_chunk_prompt(raw_content, tags_str, self.target_words)
        system_prompt = self._system_prompt()

        logger.info(
            f"Single-pass summarization | {len(raw_content)} chars | "
            f"target {self.target_words} words"
        )

        essay = self.ollama.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            top_p=0.9,
        )

        logger.info(f"Essay generated: {len(essay.split())} words")
        return essay

    # ------------------------------------------------------------------
    # Map-reduce path
    # ------------------------------------------------------------------

    def _map_reduce(self, posts: list, tags_str: str) -> str:
        """Chunk posts, summarise each, then reduce into a final essay."""
        chunks = chunk_posts(posts, self.max_context_chars)
        n = len(chunks)

        logger.info(
            f"Map-reduce summarization | {n} chunks | "
            f"max_context_chars={self.max_context_chars}"
        )
        for i, chunk in enumerate(chunks):
            chunk_chars = sum(len(getattr(p, 'text', '') or '') for p in chunk)
            logger.info(
                f"  Chunk {i + 1}/{n}: {len(chunk)} posts, {chunk_chars} chars"
            )

        # MAP phase
        partials: list[str] = []
        for i, chunk in enumerate(chunks):
            chunk_text = "\n\n".join(
                getattr(p, 'text', '') or '' for p in chunk
            )
            logger.info(f"Summarising chunk {i + 1}/{n}...")
            partial = self._summarize_chunk(chunk_text, tags_str, chunk_index=i, total_chunks=n)
            partials.append(partial)
            logger.info(
                f"Chunk {i + 1}/{n} partial: {len(partial.split())} words"
            )

        # REDUCE phase
        if len(partials) == 1:
            # Only one chunk ended up being needed — return directly.
            return partials[0]

        logger.info(f"Reduce phase: combining {len(partials)} partial essays...")
        essay = self._reduce_partials(partials, tags_str)
        logger.info(f"Final essay: {len(essay.split())} words")
        return essay

    def _summarize_chunk(
        self,
        chunk_text: str,
        tags_str: str,
        chunk_index: int,
        total_chunks: int,
    ) -> str:
        """MAP step: summarise a single chunk into a partial essay."""
        words_per_chunk = max(200, self.target_words // total_chunks)

        prompt = f"""You are analysing part {chunk_index + 1} of {total_chunks} of a personal blog.
Write a partial thematic summary ({words_per_chunk} words) capturing the key themes,
values, and personality traits expressed in this section.

BLOG SECTION CONTENT:
{chunk_text}

TAGS: {tags_str}

INSTRUCTIONS:
- Focus on recurring themes, expressed values, and personality signals.
- Write in a neutral, analytical tone — this partial will be combined with others.
- Aim for {words_per_chunk} words (±15% acceptable).
- Do NOT begin with meta-commentary like "In this section...".

Partial summary:"""

        return self.ollama.generate(
            prompt=prompt,
            system_prompt=self._system_prompt(),
            temperature=0.5,
            top_p=0.9,
        )

    def _reduce_partials(self, partials: list[str], tags_str: str) -> str:
        """REDUCE step: merge all partial essays into one final essay."""
        combined = "\n\n---\n\n".join(
            f"[Section {i + 1}]\n{p}" for i, p in enumerate(partials)
        )

        prompt = f"""You have {len(partials)} partial thematic summaries of a personal blog.
Combine them into a single coherent personal essay of {self.target_words} words.

PARTIAL SUMMARIES:
{combined}

TAGS: {tags_str}

INSTRUCTIONS:
- Write in first person as if the author is reflecting on their own worldview.
- Synthesise all sections into a unified, flowing essay — no section headers.
- Aim for {self.target_words} words (±10% acceptable).
- Use a thoughtful, introspective tone.
- Structure with clear paragraphs exploring major themes.
- Do NOT include meta-commentary about the analysis or the sections.

Begin the essay now:"""

        return self.ollama.generate(
            prompt=prompt,
            system_prompt=self._system_prompt(),
            temperature=0.7,
            top_p=0.9,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_chunk_prompt(raw_content: str, tags_str: str, target_words: int) -> str:
        return f"""Analyze this blog content and write a personal essay ({target_words} words):

BLOG CONTENT:
{raw_content}

TAGS: {tags_str}

INSTRUCTIONS:
- Write in first person as if the author is reflecting on their own worldview
- The essay should synthesize the key themes, values, and personality from the blog
- Aim for {target_words} words (\u00b110% acceptable)
- Use a thoughtful, introspective tone
- Structure with clear paragraphs exploring major themes
- Do NOT include meta-commentary about the analysis

Begin the essay now:"""

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an expert at analysing personal blogs and synthesising their themes "
            "into coherent personal essays. You understand nuance, subtext, and the deeper "
            "meaning behind expressed ideas and interests. Write essays that are authentic, "
            "insightful, and reflect the true voice of the author."
        )
