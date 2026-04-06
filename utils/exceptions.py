"""Custom exceptions for BScraper project."""


class BScrapeException(Exception):
    """Base exception for BScraper."""
    pass


class ScrapingError(BScrapeException):
    """Raised when scraping fails."""
    pass


class AuthenticationError(ScrapingError):
    """Raised when authentication to bdsmlr.com fails."""
    pass


class OllamaError(BScrapeException):
    """Raised when Ollama communication fails."""
    pass


class ConfigError(BScrapeException):
    """Raised when configuration is invalid."""
    pass


class DeduplicationError(BScrapeException):
    """Raised during content deduplication."""
    pass
