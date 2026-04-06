"""Configuration loader for BScraper."""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from utils.exceptions import ConfigError


class ConfigLoader:
    """Loads and validates configuration from YAML file."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize config loader.
        
        Args:
            config_path: Path to YAML configuration file
        
        Raises:
            ConfigError: If config file not found
        """
        self.config_path = Path(config_path)
        
        if not self.config_path.exists():
            raise ConfigError(
                f"Config file not found: {config_path}\n"
                "Copy config.example.yaml to config.yaml and update settings."
            )
        
        self.config: Dict[str, Any] = self._load_yaml()
    
    def _load_yaml(self) -> Dict[str, Any]:
        """Load YAML configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            if not config:
                raise ConfigError("Configuration file is empty")
            return config
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "scraper.proxy.enabled")
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_scraper_config(self) -> Dict[str, Any]:
        """Get scraper configuration."""
        return self.config.get('scraper', {})
    
    def get_summarizer_config(self) -> Dict[str, Any]:
        """Get summarizer configuration."""
        return self.config.get('summarizer', {})
    
    def get_traits_config(self) -> Dict[str, Any]:
        """Get traits configuration."""
        return self.config.get('traits', {})
    
    def get_output_config(self) -> Dict[str, Any]:
        """Get output configuration."""
        return self.config.get('output', {})
