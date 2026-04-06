#!/usr/bin/env python3
"""Test script for BScraper components."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all modules can be imported."""
    try:
        from utils.config_loader import ConfigLoader
        from utils.logger import setup_logger
        from utils.exceptions import BScrapeException

        from scraper.session_manager import SessionManager
        from scraper.bdsmlr_scraper import BdsmlrScraper
        from scraper.models import BlogPost

        from processor.deduplicator import ContentDeduplicator
        from processor.aggregator import ContentAggregator

        from ai_engine.ollama_client import OllamaClient
        from ai_engine.summarizer import EssaySummarizer
        from ai_engine.trait_extractor import PersonalityTraitExtractor

        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_config_loading():
    """Test configuration loading."""
    try:
        from utils.config_loader import ConfigLoader
        config = ConfigLoader("config.example.yaml")
        scraper_config = config.get_scraper_config()
        print(f"✓ Config loaded: {len(scraper_config)} scraper settings")
        return True
    except Exception as e:
        print(f"✗ Config loading error: {e}")
        return False

def test_models():
    """Test data models."""
    try:
        from scraper.models import BlogPost, AggregatedBlogContent
        from datetime import datetime

        post = BlogPost(
            post_id="test_123",
            title="Test Post",
            content="This is test content",
            tags=["test", "blog"],
            created_at=datetime.now(),
            url="https://example.com/post/123"
        )

        aggregated = AggregatedBlogContent(
            total_posts=1,
            raw_text="Test content",
            tags=["test"],
            unique_tags={"test"}
        )

        print("✓ Data models work correctly")
        return True
    except Exception as e:
        print(f"✗ Model error: {e}")
        return False

def main():
    """Run all tests."""
    print("Running BScraper component tests...\n")

    tests = [
        ("Imports", test_imports),
        ("Config Loading", test_config_loading),
        ("Data Models", test_models),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        if test_func():
            passed += 1
        print()

    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! BScraper is ready for use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())