"""Ollama API client."""

import requests
import json
from typing import Optional
from utils.exceptions import OllamaError
from utils.logger import setup_logger

logger = setup_logger('ai_engine.ollama', 'logs/ai_engine.log')


class OllamaClient:
    """Client for interacting with Ollama API."""

    def __init__(self, base_url: str, model: str, timeout: int = 120):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server base URL (e.g., http://localhost:11434)
            model: Model name to use
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        use_json_format: bool = False,
    ) -> str:
        """
        Generate text using Ollama.

        Args:
            prompt: Input prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            top_p: Nucleus sampling parameter
            use_json_format: When True, passes format='json' to constrain output to valid JSON

        Returns:
            Generated text

        Raises:
            OllamaError: If generation fails
        """
        try:
            url = f"{self.base_url}/api/generate"

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p,
                },
            }

            if use_json_format:
                payload["format"] = "json"
                logger.debug("JSON format mode enabled for this request")

            if system_prompt:
                payload["system"] = system_prompt

            logger.info(f"Calling Ollama model: {self.model}")

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )

            response.raise_for_status()

            result = response.json()
            generated_text = result.get('response', '')

            logger.info(f"Generated {len(generated_text)} characters")

            return generated_text

        except requests.RequestException as e:
            raise OllamaError(f"Ollama request failed: {e}")
        except json.JSONDecodeError as e:
            raise OllamaError(f"Invalid JSON from Ollama: {e}")

    def check_connection(self) -> bool:
        """
        Check if Ollama server is reachable.

        Returns:
            True if connection successful

        Raises:
            OllamaError: If connection fails
        """
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            logger.info("Ollama connection successful")
            return True
        except requests.RequestException as e:
            raise OllamaError(f"Cannot connect to Ollama at {self.base_url}: {e}")
