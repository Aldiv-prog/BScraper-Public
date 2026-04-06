"""Personality trait extraction engine."""

import json
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from ai_engine.ollama_client import OllamaClient
from utils.exceptions import OllamaError
from utils.logger import setup_logger

logger = setup_logger('ai_engine.traits', 'logs/ai_engine.log')


class TraitModel(BaseModel):
    """Data model for a personality trait."""
    name: str
    confidence: int = Field(ge=0, le=100)
    evidence: str
    quote: str


class TraitExtractionResponse(BaseModel):
    """Data model for trait extraction response."""
    traits: List[TraitModel]


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

    def generate_traits_from_content(
        self,
        raw_content: str,
        tags: List[str]
    ) -> None:
        """
        Generate personality traits from raw blog content and write to raw log file.

        This method calls Ollama to analyze the raw content and writes the raw response
        to logs/ai_engine_trait_response_raw.txt for later parsing.

        Args:
            raw_content: Raw aggregated blog content
            tags: List of blog tags for context
        """
        all_traits = self.base_traits + self.custom_traits
        traits_list = "\n".join(f"- {t}" for t in all_traits)
        tags_str = ", ".join(tags) if tags else "no tags"

        prompt = f"""Analyze this blog content and identify personality traits present in the author.

BLOG CONTENT:
{raw_content}

TAGS: {tags_str}

TRAITS TO EVALUATE:
{traits_list}

TASK:
From the traits list above, identify the TOP {min(len(all_traits), 20)} traits that best describe the author based on the content and tags.

Return your answer as a JSON object with this exact structure:
{{
  "traits": [
    {{
      "name": "Trait Name",
      "confidence": 85,
      "evidence": "brief explanation",
      "quote": "direct quote from content"
    }},
    {{
      "name": "Another Trait",
      "confidence": 75,
      "evidence": "brief explanation", 
      "quote": "direct quote from content"
    }}
  ]
}}

IMPORTANT: Return ONLY the JSON object. Do not include any markdown formatting, code blocks, backticks, or additional text. The response must be valid JSON that starts with {{ and ends with }}."""

        system_prompt = """You are an expert psychologist and personality analyst.
You excel at identifying psychological traits from written content with nuance and accuracy.
Provide balanced, evidence-based trait assessments.
Always cite direct evidence from the text.
Return ONLY valid JSON. Do not include markdown, code blocks, backticks, or any text outside the JSON structure."""

        logger.info(f"Generating traits from raw blog content via Ollama for {len(all_traits)} traits...")

        response_text = self.ollama.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            top_p=0.9
        )

        # Write raw response to log file
        import os
        log_path = os.path.join('logs', 'ai_engine_trait_response_raw.txt')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('\n\n--- NEW RESPONSE ---\n')
            f.write(response_text)
            f.write('\n--- END RESPONSE ---\n')

        logger.info(f"Raw trait response written to {log_path}")

    def extract_traits(self) -> List[Dict[str, Any]]:
        """
        Extract personality traits from the raw Ollama response log file.

        This method reads from logs/ai_engine_trait_response_raw.txt and parses
        the traits using robust fallback parsing strategies.

        Returns:
            List of trait dictionaries with name, confidence, evidence, quote
        """
        import os
        raw_log_path = os.path.join('logs', 'ai_engine_trait_response_raw.txt')
        if not os.path.exists(raw_log_path):
            logger.error(f"No raw trait response log found at {raw_log_path}")
            raise OllamaError(f"No raw trait response log found at {raw_log_path}")

        # Read the raw response
        try:
            with open(raw_log_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(raw_log_path, 'r', encoding='windows-1252') as f:
                content = f.read()

        # Get the last response
        responses = content.split('--- NEW RESPONSE ---')
        last_resp = responses[-1].replace('--- END RESPONSE ---', '').strip()

        # Parse the response
        traits = self._parse_response(last_resp)

        # Filter by confidence threshold
        filtered_traits = [
            t for t in traits
            if t['confidence'] >= self.confidence_threshold
        ]

        logger.info(
            f"Extracted {len(filtered_traits)} traits above {self.confidence_threshold}% confidence from raw logs"
        )

        return filtered_traits

    def _extract_json_object(self, text: str) -> Optional[str]:
        """Extract first valid JSON object or array from text using bracket/brace matching."""
        # Try to find JSON object first
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

        # If no object found, try to find JSON array
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
        # Remove all non-printable characters except newlines, tabs, carriage returns
        json_str = ''.join(
            c for c in json_str
            if c.isprintable() or c in '\n\r\t'
        )

        # Convert smart quotes and control sequences to standard quotes
        json_str = json_str.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")
        json_str = json_str.replace('…', '...').replace('–', '-').replace('—', '-')
        # Also handle other smart quote variants
        json_str = json_str.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')

        # Escape stray backslashes that are not part of valid JSON escapes
        json_str = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)

        # Normalize trailing commas before closing braces/brackets
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # Fix missing commas between consecutive object properties
        json_str = re.sub(r'([\]}\w"])\s*\n\s*"', r'\1,\n"', json_str)
        json_str = re.sub(r'([\]}\w"])\s+"(?=[^:]*:)', r'\1,"', json_str)

        # Quote bare JSON keys
        json_str = re.sub(r'(?<![\"\w])traits(?=\s*:)', '"traits"', json_str)
        json_str = re.sub(r'(?<![\"\w])name(?=\s*:)', '"name"', json_str)
        json_str = re.sub(r'(?<![\"\w])confidence(?=\s*:)', '"confidence"', json_str)
        json_str = re.sub(r'(?<![\"\w])evidence(?=\s*:)', '"evidence"', json_str)
        json_str = re.sub(r'(?<![\"\w])quote(?=\s*:)', '"quote"', json_str)

        # Convert single-quoted strings to double-quoted strings
        json_str = re.sub(r"'(.*?)'", r'"\1"', json_str)

        # More robust approach: Find all string values and escape quotes within them
        # This handles cases where quotes in string values are not properly escaped
        def escape_quotes_in_string(match):
            # match.group(1) is the content between quotes
            content = match.group(1)
            # Escape any unescaped quotes in the content
            escaped = content.replace('"', '\\"')
            return f'"{escaped}"'

        # Pattern to match string values: "content" where content may contain unescaped quotes
        # This is tricky because we need to match the opening quote, then everything until the closing quote
        # But the content might contain escaped quotes already
        json_str = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', escape_quotes_in_string, json_str)

        return json_str

    def _parse_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse Ollama response JSON.

        Args:
            response_text: Raw response from Ollama

        Returns:
            List of parsed trait dictionaries

        Raises:
            OllamaError: If response cannot be parsed
        """
        # Strip markdown code blocks if present
        response_text = re.sub(r'```\w*\n?', '', response_text)
        response_text = re.sub(r'```', '', response_text)

        # Try to parse as simple text format first
        traits = self._parse_simple_text_format(response_text)
        if traits:
            filtered_traits = [t for t in traits if t['confidence'] >= self.confidence_threshold]
            logger.info(f"Parsed {len(filtered_traits)} traits from simple text format")
            return filtered_traits

        # Try direct regex extraction from JSON-like text
        traits = self._extract_traits_from_json_text(response_text)
        if traits:
            filtered_traits = [t for t in traits if t['confidence'] >= self.confidence_threshold]
            logger.info(f"Extracted {len(filtered_traits)} traits from JSON-like text")
            return filtered_traits

        # Fallback to JSON parsing
        json_str = self._extract_json_object(response_text)
        if not json_str:
            logger.error("No JSON object found in Ollama response")
            logger.debug(f"Raw response: {response_text}")
            # Try regex extraction as fallback
            traits = self._extract_traits_with_regex(response_text)
            if traits:
                filtered_traits = [t for t in traits if t['confidence'] >= self.confidence_threshold]
                logger.info(f"Regex fallback: Extracted {len(filtered_traits)} traits above {self.confidence_threshold}% confidence")
                return filtered_traits
            raise OllamaError("Failed to parse trait extraction response: No JSON found")

        json_str = self._sanitize_json_string(json_str)

        try:
            response_data = json.loads(json_str)

            # Handle both formats: direct array or object with "traits" key
            if isinstance(response_data, list):
                # Direct array format
                traits_data = response_data
                logger.info(f"Parsed direct array format with {len(traits_data)} traits")
            elif isinstance(response_data, dict) and "traits" in response_data:
                # Object format with traits key
                traits_data = response_data["traits"]
                logger.info(f"Parsed object format with {len(traits_data)} traits")
            else:
                logger.error(f"Unexpected JSON structure: {type(response_data)}")
                logger.debug(f"Response data keys: {response_data.keys() if isinstance(response_data, dict) else 'not dict'}")
                # Try regex extraction as fallback
                traits = self._extract_traits_with_regex(response_text)
                if traits:
                    filtered_traits = [t for t in traits if t['confidence'] >= self.confidence_threshold]
                    logger.info(f"Regex fallback: Extracted {len(filtered_traits)} traits above {self.confidence_threshold}% confidence")
                    return filtered_traits
                raise ValueError("Unexpected JSON structure")

            # Validate and convert to TraitModel format
            validated_traits = []
            for trait_dict in traits_data:
                # Ensure required fields are present
                if not all(k in trait_dict for k in ["name", "confidence", "evidence", "quote"]):
                    logger.warning(f"Skipping incomplete trait: {trait_dict}")
                    continue
                trait_model = TraitModel(**trait_dict)
                validated_traits.append(trait_model.dict())

            logger.info(f"Successfully validated {len(validated_traits)} traits")
            filtered_traits = [t for t in validated_traits if t['confidence'] >= self.confidence_threshold]
            return filtered_traits

        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode failed, attempting relaxed parsing: {e}")

            # Log raw response for debugging non-standard JSON
            try:
                with open('logs/ai_engine_trait_response_raw.txt', 'a', encoding='utf-8') as f:
                    f.write('\n\n--- NEW RESPONSE ---\n')
                    f.write(response_text)
                    f.write('\n--- END RESPONSE ---\n')
            except Exception as file_exc:
                logger.warning(f"Could not write raw response file: {file_exc}")

            # Try a second pass after escaping newline characters inside JSON string
            relaxed = json_str.replace('\n', '\\n').replace('\r', '\\r')
            try:
                response_data = json.loads(relaxed)
                parsed = TraitExtractionResponse(**response_data)
                return [t.dict() for t in parsed.traits]
            except Exception as inner_e:
                logger.error(f"Relaxed JSON parsing failed: {inner_e}")

            # Fallback: attempt naive regex extraction from original response
            traits = []
            # More robust regex that can handle various quote types and formatting
            trait_pattern = r'"name"\s*:\s*["""]\s*([^""]+)\s*["""]\s*,\s*"confidence"\s*:\s*(\d+)\s*,\s*"evidence"\s*:\s*["""]\s*([^""]*)\s*["""]\s*,\s*"quote"\s*:\s*["""]\s*([^""]*)\s*["""]'
            for m in re.finditer(trait_pattern, response_text, re.DOTALL | re.IGNORECASE):
                name = m.group(1).strip()
                confidence = int(m.group(2))
                evidence = m.group(3).strip()
                quote = m.group(4).strip()

                # Clean up smart quotes and other issues
                name = name.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')
                evidence = evidence.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')
                quote = quote.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')

                traits.append({
                    'name': name,
                    'confidence': confidence,
                    'evidence': evidence,
                    'quote': quote,
                })

            logger.info(f"Regex extracted {len(traits)} traits")
            if traits:
                logger.warning("Parsed traits with fallback regex parser")

            logger.error(f"Failed to parse trait response: {e}")
            logger.debug(f"Raw response: {response_text}")
            raise OllamaError(f"Failed to parse trait extraction response: {e}")

        except ValueError as e:
            logger.error(f"Failed to parse trait response: {e}")
            logger.debug(f"Raw response: {response_text}")
            raise OllamaError(f"Failed to parse trait extraction response: {e}")

    def _extract_traits_with_regex(self, response_text: str) -> List[Dict[str, Any]]:
        """Extract traits using regex patterns as fallback."""
        traits = []
        # More robust regex that can handle various quote types and formatting
        trait_pattern = r'"name"\s*:\s*["""]\s*([^""]+)\s*["""]\s*,\s*"confidence"\s*:\s*(\d+)\s*,\s*"evidence"\s*:\s*["""]\s*([^""]*)\s*["""]\s*,\s*"quote"\s*:\s*["""]\s*([^""]*)\s*["""]'
        for m in re.finditer(trait_pattern, response_text, re.DOTALL | re.IGNORECASE):
            name = m.group(1).strip()
            confidence = int(m.group(2))
            evidence = m.group(3).strip()
            quote = m.group(4).strip()

            # Clean up smart quotes and other issues
            name = name.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')
            evidence = evidence.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')
            quote = quote.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')

            traits.append({
                'name': name,
                'confidence': confidence,
                'evidence': evidence,
                'quote': quote,
            })

        logger.info(f"Regex extracted {len(traits)} traits")
        return traits

    def _extract_traits_from_json_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract traits from JSON-like text using robust regex patterns."""
        traits = []

        # Clean up the text first
        text = text.strip()
        text = re.sub(r'```\w*\n?', '', text)
        text = re.sub(r'```', '', text)

        # Look for trait objects in the text
        # Pattern to match {"name": "...", "confidence": ..., "evidence": "...", "quote": "..."}
        trait_pattern = r'\{\s*"name"\s*:\s*["""]\s*([^""]+)\s*["""]\s*,\s*"confidence"\s*:\s*(\d+)\s*,\s*"evidence"\s*:\s*["""]\s*([^""]*)\s*["""]\s*,\s*"quote"\s*:\s*["""]\s*([^""]*)\s*["""]\s*\}'

        for match in re.finditer(trait_pattern, text, re.DOTALL | re.IGNORECASE):
            name = match.group(1).strip()
            confidence = int(match.group(2))
            evidence = match.group(3).strip()
            quote = match.group(4).strip()

            # Clean up smart quotes and other issues
            name = name.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')
            evidence = evidence.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')
            quote = quote.replace('"', '"').replace('"', '"').replace('"', '"').replace('"', '"')

            traits.append({
                'name': name,
                'confidence': confidence,
                'evidence': evidence,
                'quote': quote,
            })

        logger.info(f"JSON text extraction found {len(traits)} traits")
        return traits

    def _parse_simple_text_format(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse simple text format: TRAIT: name\nCONFIDENCE: score\nEVIDENCE: text\nQUOTE: text"""
        traits = []

        # Split by TRAIT: to find each trait block
        trait_blocks = re.split(r'TRAIT:\s*', response_text)

        for block in trait_blocks[1:]:  # Skip the first empty part
            lines = block.strip().split('\n')
            if len(lines) < 4:
                continue

            trait_dict = {}

            for line in lines[:4]:  # Only process first 4 lines
                if line.startswith('TRAIT:'):
                    trait_dict['name'] = line.replace('TRAIT:', '').strip()
                elif line.startswith('CONFIDENCE:'):
                    try:
                        confidence_str = line.replace('CONFIDENCE:', '').strip()
                        # Extract just the number
                        confidence_match = re.search(r'(\d+)', confidence_str)
                        if confidence_match:
                            trait_dict['confidence'] = int(confidence_match.group(1))
                        else:
                            trait_dict['confidence'] = 50  # Default
                    except ValueError:
                        trait_dict['confidence'] = 50
                elif line.startswith('EVIDENCE:'):
                    trait_dict['evidence'] = line.replace('EVIDENCE:', '').strip()
                elif line.startswith('QUOTE:'):
                    trait_dict['quote'] = line.replace('QUOTE:', '').strip()

            # Only add if we have all required fields
            if all(k in trait_dict for k in ['name', 'confidence', 'evidence', 'quote']):
                traits.append(trait_dict)

        return traits
