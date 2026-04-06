# BScraper - Blog Content Extraction & AI Analysis Backend

## Project Overview
BScraper is a Python-based backend for extracting blog content from bdsmlr.com and generating AI-powered psychological insights. **MVP scope**: Scraping text posts + tags → Summarization → Personality trait inference with evidence. This is the **backend only**; the frontend (web-based quiz) is a separate repository.

## Architecture: Three-Phase Pipeline
```
Phase 1: SCRAPER        Phase 2: SUMMARIZER         Phase 3: TRAIT INFERENCE
Blog content    →   Raw text + tags    →   500-1000 word essay    →   ~20 traits with evidence
(authenticated)     (deduplicated)       (via Ollama)               (JSON with quotes)
                                                                      ↑ Traits from raw content
```

**Phase 3 Key Detail**: Traits are extracted directly from the **raw aggregated blog content** (not from the essay). This preserves original author voice and intent, avoiding any distortion from the summarization process.

**Phase 1 Features:**
- **Interactive Session Control**: User can pause/resume scraping at any point
- **Infinite Scroll Support**: Handles paginated posts that load on scroll
- **Session Persistence**: Saves scraping progress to `output/scraping_session.json`
- **Content Filtering**: 
  - `text_clear`: Explicit relationship rules → used for trait inference
  - `image_dependent`: Short posts dependent on images → skipped
  - `quiz_question`: Tagged with "quiz" → saved for Phase 2
- **Graceful Degradation**: Stopping scraping doesn't terminate the app; offers to continue analysis

**Key Separation of Concerns**:
- `scraper/` - Handles bdsmlr.com authentication, HTTP requests (with proxy), HTML parsing
- `scraper/models.py` - BlogPost and ScrapingSession dataclasses with persistence
- `processor/` - Text cleaning, deduplication, aggregation, content filtering
- `ai_engine/` - Ollama integration, prompt engineering, trait extraction
- `config/` - YAML-based configuration (credentials prompted at runtime)
- `utils/` - Configuration loading, custom exceptions, colored logging
- `output/` - Generated essay (plain text `.txt`), traits (JSON), quiz questions (JSON), session state
- `logs/` - Structured JSON logs with colored console output

## Advanced Scraping Features

### Interactive Session Control
- **User Prompts**: During scraping, users can input 'c' to continue, 's' to stop and proceed to analysis, 'q' to quit entirely
- **Session Persistence**: Progress saved to `output/scraping_session.json` with post count, last URL, and timestamp
- **Resume Capability**: On restart, offers to resume from last saved position
- **Graceful Degradation**: Stopping doesn't terminate; allows proceeding to summarization/trait inference

### Infinite Scroll and Sideblog Strategy
- **Preferred Path**: Uses `/sideblog/{blogid}` endpoint for AJAX-based loading
- **Fallback**: Pagination via `/blog/{username}/page/{n}` if sideblog fails
- **End-of-blog Detection**: Determined by empty AJAX responses from the sideblog endpoint, not UI loading indicators
- **Configurable Timeout**: `loading_indicator_timeout` is present in config for legacy compatibility but the current scraper path relies on AJAX response content

### Content Classification System
- **Content Types**:
  - `text_clear`: Posts with explicit relationship content → included in trait inference
  - `image_dependent`: Short posts relying on images → skipped
  - `quiz_question`: Posts tagged with "quiz" → saved to `output/quiz_questions.json` for future quiz generation
- **Tag Processing**: Extracts tags from post links, removes '#' prefix
- **Trait Filter Map**: Maps tags to personality traits for correlation analysis

### Session Management
- **ScrapingSession Dataclass**: Tracks posts scraped, last position, timestamps
- **Persistence**: JSON serialization for cross-run continuity
- **Interactive Control**: `_scrape_with_session_control()` handles user input during scraping

## Configuration (config.yaml)
```yaml
scraper:
  # bdsmlr.com connection settings
  base_url: "https://bdsmlr.com"
  blog_name: "education.bdsmlr.com"  # Blog name to scrape (may differ from login username)
  request_delay: 2  # seconds between requests
  timeout: 30  # request timeout in seconds (increased for proxy)
  verify_ssl: false   # set false to disable SSL cert validation (dev only)
  interactive_scraping: true  # Enable interactive session control during scraping
  loading_indicator_timeout: 20  # seconds to wait for loading indicator to disappear (detects end of blog)
  
  # Proxy configuration
  proxy:
    enabled: true
    url: "http://proxy-server:port"

summarizer:
  ollama_model: "gemma-3-4b-it-uncensored-v2-gguf:q5_k_m"
  ollama_url: "http://localhost:11434"
  #ollama_model: "hf.co/Andycurrent/gemma-3-4b-it-uncensored-v2-GGUF:Q5_K_M"
  # Timeout for Ollama requests (seconds)
  timeout: 120

output:
  # Essay generation settings
  essay_word_count: 300  # 500-1000 range recommended
  essay_file: "output/essay.txt"  # Plain text format (not Markdown)
  
  # Personality traits inference settings
  traits_file: "output/traits.json"
  traits_confidence_threshold: 50  # Minimum confidence (0-100) to include trait

traits:
  # Total number of traits to identify
  total_count: 20
  
  # Base psychological traits (10 fixed)
  base_traits:
    - "Dominance Orientation"
    - "Submission Orientation"
    - "Power Dynamics Awareness"
    - "Risk Tolerance"
    - "Emotional Expressiveness"
    - "Boundary Setting"
    - "Vulnerability"
    - "Authenticity"
    - "Community Engagement"
    - "Self-Reflection"
  
  # Optional: User can add custom traits (5-20 items)
  custom_traits: []  # e.g., ["Custom Trait 1", "Custom Trait 2"]
```

## Development Workflow

### Setup
```bash
python -m venv venv
venv\Scripts\activate  # Windows PowerShell
pip install -r requirements.txt
```

### Run MVP Pipeline
```bash
python main.py
# Prompts: "Enter bdsmlr.com username: " → "Enter password: "
# Outputs: 
#   - output/essay.txt (plain text personal essay, ~300 words)
#   - output/traits.json (psychological traits with confidence & evidence)
#   - output/quiz_questions.json (extracted quiz questions from blog)
#   - output/scraping_session.json (session state for resuming)
```

### CLI Phase Control
- `python main.py --phase all` — run the full pipeline (scrape, summarize, traits)
- `python main.py --phase scrape` — run scraping only and save session state
- `python main.py --phase summarize --resume` — use existing scraping session to generate the essay; resume incomplete scraping automatically if needed
- `python main.py --phase traits` — run trait extraction from raw blog content (requires saved scraping session)
- `python main.py --phase all --resume` — resume an incomplete scraping session automatically before continuing analysis
- `python main.py --session-file custom_session.json` — use a custom session storage path

**Trait Extraction Behavior** (Phase 3):
- **Source**: Traits are extracted directly from **raw aggregated blog content** (scraped posts), not from the essay
- **Process**: Raw content → Ollama inference → JSON response → Parse & filter by confidence
- **Output**: Saves all traits above the configured `traits_confidence_threshold` (default 50%) to `output/traits.json`
- **Advantages**: Preserves original author voice, avoids summarization distortion, extracts authentic personality traits
- **Raw Logs**: Ollama responses written to `logs/ai_engine_trait_response_raw.txt` for review/debugging

### Debug
- Use `--verbose` flag for detailed logging
- Check `logs/scraper.log` for network/parsing issues
- Check `logs/ai_engine.log` for Ollama communication
- Check `logs/ai_engine_trait_response_raw.txt` for raw model responses (used by traits phase)

## Key Patterns

### 1. Ollama Integration (ai_engine/)
- **Local-only**: No external API calls; Ollama runs on `localhost:11434`
- **Prompt Structure**: 
  ```python
  # Phase 2: Summarization prompt (include raw blog content)
  prompt = f"""Analyze this blog content and write a personal essay (300 words):
  {raw_blog_content}
  
  The essay should reflect the author's worldview, values, and personality."""
  
  # Phase 3: Trait inference prompt (work from raw blog content, NOT essay)
  prompt = f"""Analyze this blog content and identify personality traits:
  {raw_blog_content}
  
  TAGS: {tags}
  
  For EACH trait, provide:
  - Trait name
  - Confidence (0-100)
  - Direct evidence/quote from content"""
  ```
- **Response Parsing**: Expect structured JSON output; validate with Pydantic models

### 2. Scraper Authentication
- **Runtime Prompts**: Use `getpass.getpass()` for password input (not echoed to terminal)
- **Session Management**: Maintain `requests.Session()` with cookies for authenticated requests
- **CSRF Handling**: Extract CSRF tokens from login forms using regex patterns
- **Browser Headers**: Include realistic User-Agent and Accept headers to avoid blocking
- **Proxy Rotation**: If `scraper.proxy.enabled=true`, apply proxy to ALL requests
- **Interactive Control**: `scrape_blog_interactive()` handles user input for pause/resume/quit

### 3. HTML Parsing Patterns (bdsmlr_scraper.py)
- **Multiple Selectors**: Try different CSS selectors for post containers (`article.post`, `div.entry`, etc.)
- **Flexible Content Extraction**: Handle various blog layouts with fallback selectors
- **Tag Parsing**: Extract tags from post links, removes '#' prefix
- **Date Parsing**: Support multiple datetime formats (ISO, US, European)
- **URL Construction**: Prefer `/sideblog/{blogid}` for AJAX loading; fallback to `/blog/{username}/page/{n}` for pagination
- **Loading Detection**: `_detect_loading_with_timeout()` and `_detect_loading_with_scroll()` for infinite scroll handling

### 4. Content Deduplication
- Posts may repeat or have minor variations; deduplicate by content hash before summarization
- Store hashes in temporary JSON file during scraping

## Trait Inference & Quiz Integration

### Current Trait Extraction Modes

**Mode 1: "Evaluate" (Current - Predefined Traits)**
- Scores raw blog content against a predefined set of base traits
- Output: 20 traits (10 base + 10 custom) with confidence scores, evidence, and quotes
- Source: Raw aggregated blog content (preserves author voice, avoids summarization bias)
- Process: Raw content → Ollama inference → JSON response → Parse & filter by confidence
- Output file: `output/traits.json`
- Confidence threshold: 50% minimum (configurable)
- Advantages: Consistent evaluation framework, repeatable scoring

**Mode 2: "Discover" (Planned - Unbiased Trait Discovery)**
- Discovers top-confidence traits directly from raw content WITHOUT predefined constraints
- Purpose: Identify most prominent personality traits organically
- Output: 5-10 top-confidence traits without preset bias
- Source: Same raw blog content, but using general psychological trait framework
- Advantages: Unbiased discovery, reveals authentic/unexpected traits
- Timeline: High priority, parallel with quiz integration
- Will leverage: Ollama's general knowledge of psychology + content analysis

### Quiz Questions Integration
- **Current Status**: Quiz questions extracted and saved to `output/quiz_questions.json`
- **Future Role**: Central to trait validation workflow
- **Planned Workflow**: 
  1. Extract quiz questions from blog (already working)
  2. Generate quiz based on extracted questions + inferred traits
  3. Present quiz to users (frontend integration)
  4. Score responses against trait predictions
  5. Adjust trait confidence scores based on quiz performance
- **Target**: Use quiz results to validate/refine trait inference

### Output Format (traits.json)
```json
{
  "traits": [
    {
      "name": "Dominance Orientation",
      "confidence": 87,
      "evidence": "The author frequently discusses leadership roles and decision-making authority",
      "quote": "\"I believe in taking control and guiding others toward my vision\""
    }
  ],
  "summary_reference": "logs/ai_engine_trait_response_raw.txt",
  "generated_at": "2026-04-06T14:32:00Z"
}
```

### Quiz Questions Output (quiz_questions.json)
```json
[
  {
    "post_id": "12345",
    "content": "What is your favorite position in BDSM?",
    "tags": ["education", "bdsm"],
    "extracted_at": "2026-04-06T10:15:00Z"
  }
]
```
- Questions extracted from blog posts tagged with "quiz"
- Used for trait evaluation loop (Phase 2 future work)
- Ready for quiz generation and scoring integration

### Prompting Strategy for Trait Extraction
1. **Phase 3 Approach**: Analyze raw blog content directly (not the essay)
2. **Evidence Required**: Each trait must include specific quotes or examples
3. **Confidence Scoring**: Numeric 0-100 confidence; discard below threshold (default 50%)
4. **Evaluate Mode**: Score against predefined base_traits list for consistency
5. **Discover Mode** (planned): Return top traits without predefined constraint
6. **JSON Format**: Strict JSON response for reliable parsing

## Integration Points
- **bdsmlr.com**: Requires valid username/password (private blog access)
- **Ollama**: Must be running locally (`ollama serve` before running this app)
- **Proxy Server**: Optional; set in config if needed for network isolation

## Common Issues & Solutions

- **Ollama Timeout**: Increase timeout in config (tested stable up to 300 posts)
- **HTML Structure Changes**: If scraper breaks, examine bdsmlr.com structure and update CSS selectors in `scraper/bdsmlr_scraper.py`
- **Trait Output Quality**: Verify Ollama response is valid JSON; check `logs/ai_engine_trait_response_raw.txt` for raw model output
- **Duplicate Detection**: Based on content hash; verify `logs/scraper.log` for post ID consistency
- **Session Resume Issues**: Post IDs should always be numeric strings; check logs if resuming adds duplicates
- **Essay Format**: Outputs as plain text `.txt` file (configurable via `essay_file` in config.yaml)

## File Organization
```
BScraper-Backend/
├── config.yaml              # User configuration (ignored in git)
├── config.example.yaml      # Template for users
├── main.py                  # Entry point
├── scraper/
│   ├── bdsmlr_scraper.py    # Authentication + HTML parsing + interactive scraping
│   ├── session_manager.py   # Cookie/session handling
│   └── models.py            # Post and session dataclasses
├── processor/
│   ├── deduplicator.py      # Hash-based deduplication
│   └── aggregator.py        # Content aggregation + tag processing
├── ai_engine/
│   ├── ollama_client.py     # Ollama API wrapper
│   ├── summarizer.py        # Essay generation
│   └── trait_extractor.py   # Trait inference with confidence filtering
├── utils/
│   ├── config_loader.py     # YAML configuration loading
│   ├── exceptions.py        # Custom exception hierarchy
│   └── logger.py            # Colored logging setup
├── output/
│   ├── essay.txt            # Generated essay (plain text)
│   ├── traits.json          # Inferred traits with evidence and confidence
│   ├── quiz_questions.json  # Extracted quiz questions for trait validation
│   └── scraping_session.json # Session persistence data
├── logs/
│   ├── scraper.log          # Scraping operation logs
│   ├── ai_engine.log        # AI processing logs
│   └── ai_engine_trait_response_raw.txt # Raw Ollama responses (used by traits phase)
└── docs/                    # Documentation files
    ├── CHECKLIST.md
    ├── CODE_CHANGES.md
    ├── COLORED_LOGGING.md
    ├── CONFIG_REFERENCE.md
    ├── FIX_SUMMARY.md
    ├── FLOWCHART.md
    ├── IMPLEMENTATION_NOTES.md
    ├── INFINITE_SCROLL.md
    ├── INTERACTIVE_SCRAPING.md
    ├── LOADING_DETECTION.md
    ├── LOADING_FIX.md
    ├── PROJECT_STRUCTURE.md
    ├── README.md
    ├── SSL_WARNING_FIX.md
    └── test_components.py
```

## Conventions
- **Code Style**: PEP 8 + type hints on all functions
- **Error Handling**: Custom exceptions (`ScrapingError`, `OllamaError`, `ConfigError`)
- **Logging**: Structured JSON logs; INFO for milestones, WARNING for retries, ERROR for failures
- **Secrets**: Never commit credentials; prompt at runtime or use environment variables