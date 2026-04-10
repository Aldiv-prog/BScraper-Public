# Changelog

All notable changes to BScraper are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.3.0] — 2026-04-10

### Summary
Stable merge of `feature/massedit-scraper` into `main`. MassEditor scraping mode fully integrated, structured JSON trait extraction via Ollama `format:json`, and phase-gated re-analyze submenu.

### Added
- **MassEditor scraping mode** (`--massedit` CLI flag, Issue #16): scrapes bdsmlr blog via the dashboard MassEditor panel instead of the standard post feed, with dashboard side-blog context switching before scraping begins
- **MassEditor-aware `content_type` classification** in `BdsmlrScraper._classify_content_type`: detects `quiz_question` posts and overrides classification accordingly
- **`inspect_scraping_session.py`** helper script: summarises `content_type` distribution by post-length buckets for debugging classification behaviour
- **Re-analyze submenu** in `main.py`: after selecting "Re-analyze existing data", a new contextual menu offers:
  - Run full analysis (summarization + trait extraction)
  - Run summarization only
  - Run trait extraction only
  - Back to previous menu
- **Phase-gated pipeline**: `--phase` CLI flag now properly controls which phases execute (`all` / `summarize` / `traits`)
- **Structured JSON trait extraction** (Issue #18 §3): `OllamaClient.generate()` gains `use_json_format` param; when `True`, adds `format:json` to the Ollama payload and parses the response directly with `json.loads()`
- **In-memory `_last_traits` store** in `PersonalityTraitExtractor`: eliminates the file round-trip loss between raw AI log and `traits.json`; `extract_traits()` checks in-memory store first, falls back to file for backward compatibility
- Single retry on `JSONDecodeError` with raw response logged to `ai_engine_trait_response_raw.txt`

### Fixed
- **`UnicodeEncodeError` (charmap)**: essay and traits output files now explicitly opened with `encoding='utf-8'`
- **MassEditor end-of-blog detection**: pagination now checks for a disabled "Next" button instead of relying on page count alone

---

## [0.2.0] — 2026-04-07 / 2026-04-08

### Summary
Session backup and archival management system. Merged via PR #1 (`ProcessControl` branch).

### Added
- **`ArchivalManager`**: saves and loads complete analysis sessions (scraping + aggregated content + essay + traits + metadata) as JSON archives under `archives/`
- **Session backup system**: `--save-session-backup`, `--list-session-backups`, `--load-session-backup` CLI flags
- **Archive inspection**: `--list-archives`, `--load-archive` CLI flags with interactive session inspector (content breakdown, tags, top traits, essay preview)
- **`CompleteAnalysisSession`** data model for archivable sessions

---

## [0.1.0] — 2026-04-06

### Summary
Initial foundation commit. Core scraper architecture, data models, authentication, configuration, logging, and AI engine scaffolding.

### Added
- **Data models** (`scraper/models.py`): `BlogPost`, `AggregatedBlogContent`, `ScrapingSession` with serialization and file I/O methods
- **`SessionManager`** (`scraper/session_manager.py`): bdsmlr.com authentication, CSRF token extraction, session-aware GET/POST requests
- **`BdsmlrScraper`**: paginated blog scraping with resume support, multiple HTML selectors, rate limiting, and `content_type` classification (`text_clear`, `image_dependent`, `quiz_question`, `unknown`)
- **`ContentDeduplicator`** and **`ContentAggregator`**: deduplication and aggregation of scraped posts into `AggregatedBlogContent`
- **`OllamaClient`** and **`EssaySummarizer`**: local Ollama model integration for 500–1000 word essay generation from aggregated blog content
- **`PersonalityTraitExtractor`**: base and custom trait inference with confidence thresholds, generating structured `traits.json`
- **`ConfigLoader`** (`utils/config_loader.py`): YAML config loading and validation; `config.example.yaml` template
- **Custom exceptions** (`utils/exceptions.py`): `BScrapeException` hierarchy for typed error handling
- **Logger** (`utils/logger.py`): color-coded console output + rotating file logging (`logs/scraper.log`, `logs/ai_engine.log`)
- **`test_sanitizer.py`**: JSON sanitisation unit tests for the AI engine
- **`update_traits.py`**: utility script to parse and filter traits from raw AI engine responses

---

*BScraper is a CLI backend tool for scraping bdsmlr.com blogs and generating AI-powered personality analysis via a local Ollama model.*
