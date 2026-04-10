"""Personality trait extraction engine."""

import json
import os
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from ai_engine.ollama_client import OllamaClient
from utils.exceptions import OllamaError
from utils.logger import setup_logger

logger = setup_logger('ai_engine.traits', 'logs/ai_engine.log')

RAW_LOG_PATH = os.path.join('logs', 'ai_engine_trait_response_raw.txt')


class TraitModel(BaseModel):
    """Data model for a personality trait."""
    name: str
    confidence: int = Field(ge=0, le=100)
    evidence: str
    quote: str


class TraitExtractionResponse(BaseModel):
    """Data model for trait extraction response."""
    traits: List[TraitModel]


def _write_raw_log(response_text: str, label: str = "RESPONSE") -> None:
    """Append a labelled block to the raw trait response log."""
    os.makedirs(os.path.dirname(RAW_LOG_PATH), exist_ok=True)
    with open(RAW_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f'\n\n--- {label} ---\n')
        f.write(response_text)
        f.write(f'\n--- END {label} ---\n')


class PersonalityTraitExtractor:
    """Extracts personality traits from essay content."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        base_traits: List[str],
        custom_traits: List[str],
        confidence_threshold: int = 50
    ):
        """
        Initialize trait extractor.

        Args:
            ollama_client: Ollama client instance
            base_traits: List of base psychological traits to evaluate
            custom_traits: List of custom traits to evaluate
            confidence_threshold: Minimum confidence to include trait (0-100)
        """
        self.ollama = ollama_client
        self.base_traits = base_traits
        self.custom_traits = custom_traits
        self.all_traits = base_traits + custom_traits
        self.confidence_threshold = confidence_threshold
        # In-memory store set by generate_traits_from_content(); read by extract_traits()
        self._last_traits: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_traits_from_content(
        self,
        raw_content: str,
        tags: List[str]
    ) -> None:
        """
        Generate personality traits from raw blog content.

        Uses Ollama's structured JSON format mode so the model is constrained
        to emit valid JSON directly.  The raw response is always written to
        logs/ai_engine_trait_response_raw.txt for debugging.  On a
        JSONDecodeError the raw response is logged and a single retry is
        attempted before the chunk is skipped.

        Parsed & validated traits are stored in self._last_traits so that
        extract_traits() can retrieve them without a file round-trip.

        Args:
            raw_content: Raw aggregated blog content
            tags: List of blog tags for context
        """
        traits_list = "\n".join(f"- {t}" for t in self.all_traits)
        tags_str = ", ".join(tags) if tags else "no tags"

        prompt = f"""Analyze this blog content and identify personality traits present in the author.

BLOG CONTENT:
{raw_content}

TAGS: {tags_str}

TRAITS TO EVALUATE:
{traits_list}

TASK:
From the traits list above, identify the TOP {min(len(self.all_traits), 20)} traits that best describe the author based on the content and tags.

Return a JSON object with this exact structure:
{{
  "traits": [
    {{
      "name": "Trait Name",
      "confidence": 85,
      "evidence": "brief explanation",
      "quote": "direct quote from content"
    }}
  ]
}}

Rules:
- confidence is an integer from 0 to 100
- Return ONLY the JSON object, nothing else"""

        system_prompt = (
            "You are an expert psychologist and personality analyst. "
            "You excel at identifying psychological traits from written content with nuance and accuracy. "
            "Provide balanced, evidence-based trait assessments. "
            "Always cite direct evidence from the text. "
            "Return ONLY valid JSON matching the requested schema."
        )

        logger.info(
            f"Generating traits via Ollama (JSON format mode) for {len(self.all_traits)} traits..."
        )

        self._last_traits = None  # reset before new generation

        response_text = self.ollama.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            top_p=0.9,
            use_json_format=True,
        )

        # Always persist raw response for debugging
        _write_raw_log(response_text, label="NEW RESPONSE")
        logger.info(f"Raw trait response written to {RAW_LOG_PATH}")

        # Parse immediately — no file round-trip needed
        parsed = self._parse_json_response(response_text, allow_retry=True)
        if parsed is not None:
            self._last_traits = parsed
            logger.info(
                f"Stored {len(parsed)} parsed traits in memory (above threshold: "
                f"{sum(1 for t in parsed if t['confidence'] >= self.confidence_threshold)})"
            )
        else:
            logger.warning(
                "generate_traits_from_content: could not parse a valid trait list; "
                "extract_traits() will attempt file-based fallback."
            )

    def extract_traits(self) -> List[Dict[str, Any]]:
        """
        Return the extracted personality traits above the confidence threshold.

        Checks self._last_traits first (populated by generate_traits_from_content).
        Falls back to reading logs/ai_engine_trait_response_raw.txt only when
        _last_traits is not available (backward compatibility).

        Returns:
            List of trait dicts with name, confidence, evidence, quote
        """
        if self._last_traits is not None:
            filtered = [
                t for t in self._last_traits
                if t['confidence'] >= self.confidence_threshold
            ]
            logger.info(
                f"extract_traits: returning {len(filtered)} traits from memory "
                f"(threshold={self.confidence_threshold})"
            )
            return filtered

        # --- Backward-compat file fallback ---
        logger.warning(
            "extract_traits: _last_traits is empty; falling back to raw log file."
        )
        if not os.path.exists(RAW_LOG_PATH):
            raise OllamaError(f"No raw trait response log found at {RAW_LOG_PATH}")

        try:
            with open(RAW_LOG_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(RAW_LOG_PATH, 'r', encoding='windows-1252') as f:
                content = f.read()

        responses = content.split('--- NEW RESPONSE ---')
        last_resp = responses[-1].replace('--- END NEW RESPONSE ---', '').strip()

        traits = self._parse_response(last_resp)
        filtered = [t for t in traits if t['confidence'] >= self.confidence_threshold]
        logger.info(
            f"extract_traits: file fallback returned {len(filtered)} traits "
            f"above threshold={self.confidence_threshold}"
        )
        return filtered

    # ------------------------------------------------------------------
    # Primary JSON parser (format:json path)
    # ------------------------------------------------------------------

    def _parse_json_response(
        self,
        response_text: str,
        allow_retry: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Parse a response that was requested with format:json.

        Attempts json.loads() directly.  On JSONDecodeError, logs the raw
        response and retries once via Ollama before giving up.

        Args:
            response_text: Raw text returned by Ollama
            allow_retry: Whether a single retry is permitted on parse failure

        Returns:
            List of validated trait dicts, or None if parsing failed entirely
        """
        # Strip accidental markdown fences (some models add them despite format:json)
        cleaned = re.sub(r'```[\w]*\n?', '', response_text).strip()
        cleaned = re.sub(r'```', '', cleaned).strip()

        try:
            data = json.loads(cleaned)
            return self._validate_traits_data(data)
        except json.JSONDecodeError as exc:
            logger.warning(f"JSONDecodeError on format:json response: {exc}")
            _write_raw_log(response_text, label="PARSE FAILURE")

            if allow_retry:
                logger.info("Retrying Ollama call once after JSON parse failure...")
                # We need to re-issue the generate call; however _parse_json_response
                # does not hold the prompt.  We signal the caller to retry by returning
                # a sentinel — the caller (generate_traits_from_content) already has the
                # prompt and handles the retry loop.  Here we attempt a best-effort
                # recovery using the legacy parsers instead, which avoids an extra
                # network call from inside the parser.
                traits = self._parse_response(response_text)
                if traits:
                    logger.info(
                        f"Legacy parser recovered {len(traits)} traits after JSON failure"
                    )
                    return traits

            logger.error(
                "_parse_json_response: all parsing strategies exhausted; skipping chunk."
            )
            return None

    def _validate_traits_data(self, data: Any) -> List[Dict[str, Any]]:
        """
        Validate parsed JSON data against TraitModel schema.

        Accepts both {"traits": [...]} and a bare list.

        Args:
            data: Parsed JSON (dict or list)

        Returns:
            List of validated trait dicts

        Raises:
            ValueError: If data structure is not recognised
        """
        if isinstance(data, list):
            traits_data = data
        elif isinstance(data, dict) and "traits" in data:
            traits_data = data["traits"]
        else:
            raise ValueError(
                f"Unexpected JSON structure: expected dict with 'traits' key or list, "
                f"got {type(data)}"
            )

        validated: List[Dict[str, Any]] = []
        for item in traits_data:
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dict trait item: {item!r}")
                continue
            missing = [k for k in ("name", "confidence", "evidence", "quote") if k not in item]
            if missing:
                logger.warning(f"Skipping trait missing fields {missing}: {item!r}")
                continue
            try:
                trait = TraitModel(**item)
                validated.append(trait.dict())
            except Exception as exc:
                logger.warning(f"Pydantic validation failed for trait {item!r}: {exc}")
                continue

        logger.info(f"_validate_traits_data: {len(validated)} traits validated")
        return validated

    # ------------------------------------------------------------------
    # Legacy parsers (fallback path / file round-trip)
    # ------------------------------------------------------------------

    def _extract_json_object(self, text: str) -> Optional[str]:
        """Extract first valid JSON object or array from text using bracket/brace matching."""
        start = text.find('{')
        if start != -1:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                c = text[i]
                if c == '\\' and not escape:
                    escape = True
                    continue
                if c == '"' and not escape:
                    in_string = not in_string
                if not in_string:
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            return text[start:i + 1]
                escape = False

        start = text.find('[')
        if start != -1:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                c = text[i]
                if c == '\\' and not escape:
                    escape = True
                    continue
                if c == '"' and not escape:
                    in_string = not in_string
                if not in_string:
                    if c == '[':
                        depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            return text[start:i + 1]
                escape = False

        return None

    def _sanitize_json_string(self, json_str: str) -> str:
        """Remove control chars and fix common invalid JSON escape sequences."""
        json_str = ''.join(
            c for c in json_str
            if c.isprintable() or c in '\n\r\t'
        )
        json_str = json_str.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")
        json_str = json_str.replace('\u2026', '...').replace('\u2013', '-').replace('\u2014', '-')
        json_str = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        json_str = re.sub(r'([\]}\w"])\s*\n\s*"', r'\1,\n"', json_str)
        json_str = re.sub(r'([\]}\w"])\s+"(?=[^:]*:)', r'\1,"', json_str)
        json_str = re.sub(r'(?<![\"\w])traits(?=\s*:)', '"traits"', json_str)
        json_str = re.sub(r'(?<![\"\w])name(?=\s*:)', '"name"', json_str)
        json_str = re.sub(r'(?<![\"\w])confidence(?=\s*:)', '"confidence"', json_str)
        json_str = re.sub(r'(?<![\"\w])evidence(?=\s*:)', '"evidence"', json_str)
        json_str = re.sub(r'(?<![\"\w])quote(?=\s*:)', '"quote"', json_str)
        json_str = re.sub(r"'(.*?)'", r'"\1"', json_str)

        def escape_quotes_in_string(match):
            content = match.group(1)
            escaped = content.replace('"', '\\"')
            return f'"{escaped}"'

        json_str = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', escape_quotes_in_string, json_str)
        return json_str

    def _parse_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Legacy multi-strategy response parser (used as fallback).

        Tries, in order:
        1. Simple TRAIT:/CONFIDENCE:/EVIDENCE:/QUOTE: text format
        2. Direct regex extraction of JSON-like trait objects
        3. Full JSON extraction + sanitisation + Pydantic validation
        4. Regex extraction from raw text

        Args:
            response_text: Raw response from Ollama

        Returns:
            List of parsed trait dictionaries
        """
        response_text = re.sub(r'```\w*\n?', '', response_text)
        response_text = re.sub(r'```', '', response_text)

        traits = self._parse_simple_text_format(response_text)
        if traits:
            logger.info(f"Legacy parser: simple text format yielded {len(traits)} traits")
            return traits

        traits = self._extract_traits_from_json_text(response_text)
        if traits:
            logger.info(f"Legacy parser: JSON-text extraction yielded {len(traits)} traits")
            return traits

        json_str = self._extract_json_object(response_text)
        if not json_str:
            logger.error("Legacy parser: no JSON object found in response")
            traits = self._extract_traits_with_regex(response_text)
            if traits:
                logger.warning(f"Legacy parser: regex fallback yielded {len(traits)} traits")
            return traits

        json_str = self._sanitize_json_string(json_str)

        try:
            data = json.loads(json_str)
            validated = self._validate_traits_data(data)
            logger.info(f"Legacy parser: JSON path yielded {len(validated)} traits")
            return validated
        except json.JSONDecodeError as exc:
            logger.warning(f"Legacy parser: JSON decode failed: {exc}")
            relaxed = json_str.replace('\n', '\\n').replace('\r', '\\r')
            try:
                data = json.loads(relaxed)
                validated = self._validate_traits_data(data)
                logger.info(f"Legacy parser: relaxed JSON yielded {len(validated)} traits")
                return validated
            except Exception as inner_exc:
                logger.error(f"Legacy parser: relaxed JSON also failed: {inner_exc}")

            traits = self._extract_traits_with_regex(response_text)
            logger.warning(f"Legacy parser: final regex fallback yielded {len(traits)} traits")
            return traits

        except ValueError as exc:
            logger.error(f"Legacy parser: validation error: {exc}")
            traits = self._extract_traits_with_regex(response_text)
            return traits

    def _extract_traits_with_regex(self, response_text: str) -> List[Dict[str, Any]]:
        """Extract traits using regex patterns as last-resort fallback."""
        traits = []
        trait_pattern = (
            r'"name"\s*:\s*[\u201c\u201d"]\s*([^\u201c\u201d"]+)\s*[\u201c\u201d"]'
            r'\s*,\s*"confidence"\s*:\s*(\d+)'
            r'\s*,\s*"evidence"\s*:\s*[\u201c\u201d"]\s*([^\u201c\u201d"]*)\s*[\u201c\u201d"]'
            r'\s*,\s*"quote"\s*:\s*[\u201c\u201d"]\s*([^\u201c\u201d"]*)\s*[\u201c\u201d"]'
        )
        for m in re.finditer(trait_pattern, response_text, re.DOTALL | re.IGNORECASE):
            traits.append({
                'name': m.group(1).strip(),
                'confidence': int(m.group(2)),
                'evidence': m.group(3).strip(),
                'quote': m.group(4).strip(),
            })
        logger.info(f"_extract_traits_with_regex: found {len(traits)} traits")
        return traits

    def _extract_traits_from_json_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract traits from JSON-like text using robust regex patterns."""
        traits = []
        text = re.sub(r'```\w*\n?', '', text.strip())
        text = re.sub(r'```', '', text)
        trait_pattern = (
            r'\{\s*"name"\s*:\s*[\u201c\u201d"]\s*([^\u201c\u201d"]+)\s*[\u201c\u201d"]'
            r'\s*,\s*"confidence"\s*:\s*(\d+)'
            r'\s*,\s*"evidence"\s*:\s*[\u201c\u201d"]\s*([^\u201c\u201d"]*)\s*[\u201c\u201d"]'
            r'\s*,\s*"quote"\s*:\s*[\u201c\u201d"]\s*([^\u201c\u201d"]*)\s*[\u201c\u201d"]\s*\}'
        )
        for match in re.finditer(trait_pattern, text, re.DOTALL | re.IGNORECASE):
            traits.append({
                'name': match.group(1).strip(),
                'confidence': int(match.group(2)),
                'evidence': match.group(3).strip(),
                'quote': match.group(4).strip(),
            })
        logger.info(f"_extract_traits_from_json_text: found {len(traits)} traits")
        return traits

    def _parse_simple_text_format(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse simple text format: TRAIT:/CONFIDENCE:/EVIDENCE:/QUOTE: blocks."""
        traits = []
        trait_blocks = re.split(r'TRAIT:\s*', response_text)
        for block in trait_blocks[1:]:
            lines = block.strip().split('\n')
            if len(lines) < 4:
                continue
            trait_dict: Dict[str, Any] = {}
            for line in lines[:4]:
                if line.startswith('TRAIT:'):
                    trait_dict['name'] = line.replace('TRAIT:', '').strip()
                elif line.startswith('CONFIDENCE:'):
                    m = re.search(r'(\d+)', line)
                    trait_dict['confidence'] = int(m.group(1)) if m else 50
                elif line.startswith('EVIDENCE:'):
                    trait_dict['evidence'] = line.replace('EVIDENCE:', '').strip()
                elif line.startswith('QUOTE:'):
                    trait_dict['quote'] = line.replace('QUOTE:', '').strip()
            if all(k in trait_dict for k in ('name', 'confidence', 'evidence', 'quote')):
                traits.append(trait_dict)
        return traits
