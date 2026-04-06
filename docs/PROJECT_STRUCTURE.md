# Updated Project Structure

```
BScraper-Backend/
├── README.md                       # Main project documentation
├── INTERACTIVE_SCRAPING.md         # User guide for interactive features
├── IMPLEMENTATION_NOTES.md         # Technical implementation details
├── config.yaml                     # User configuration (credentials, settings)
├── config.example.yaml             # Template for users
├── main.py                         # Entry point - orchestrates 3-phase pipeline
│
├── scraper/
│   ├── __init__.py
│   ├── bdsmlr_scraper.py          # Blog parser + infinite scroll handler
│   │   ├── scrape_blog_interactive()    # NEW: Interactive scraper with control
│   │   ├── _scrape_with_session_control() # NEW: Main loop with user prompts
│   │   ├── _dict_to_blogpost()          # NEW: Session recovery utility
│   │   ├── _discover_blog_url()         # Blog URL discovery
│   │   ├── _parse_posts()               # HTML parsing
│   │   ├── _classify_content_type()     # Post categorization (text_clear, image_dependent, quiz)
│   │   └── _extract_*()                 # Content extraction methods
│   │
│   ├── session_manager.py          # HTTP session + authentication
│   │   ├── authenticate()               # bdsmlr.com login with CSRF
│   │   ├── get() / post()               # Authenticated requests
│   │   └── _extract_csrf_token()        # CSRF protection
│   │
│   └── models.py                   # Data structures
│       ├── BlogPost                 # Single post: id, content, tags, type
│       ├── AggregatedBlogContent    # Combined posts for AI
│       └── ScrapingSession          # NEW: Session state for resume capability
│
├── processor/
│   ├── __init__.py
│   ├── deduplicator.py              # Remove duplicate posts
│   │   ├── ContentDeduplicator
│   │   ├── deduplicate()            # Hash-based dedup
│   │   └── _hash_content()          # SHA256 hashing
│   │
│   └── aggregator.py                # Combine posts for analysis
│       ├── ContentAggregator
│       ├── aggregate()              # Separate by content_type + save quiz Qs
│       └── _save_quiz_questions()   # NEW: Save quiz-tagged posts to separate file
│
├── ai_engine/
│   ├── __init__.py
│   ├── ollama_client.py             # Ollama API wrapper
│   │   ├── OllamaClient
│   │   ├── generate()               # Prompt execution
│   │   └── check_connection()       # Verify Ollama running
│   │
│   ├── summarizer.py                # Essay generation
│   │   ├── EssaySummarizer
│   │   └── summarize()              # Convert posts → essay
│   │
│   └── trait_extractor.py           # Personality trait inference
│       ├── PersonalityTraitExtractor
│       └── extract_traits()         # Extract + score traits with evidence
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                    # Structured logging
│   │   └── setup_logger()           # Configure file + console logging
│   │
│   ├── config_loader.py             # YAML configuration
│   │   └── ConfigLoader
│   │
│   └── exceptions.py                # Custom exceptions
│       ├── BScrapeException
│       ├── AuthenticationError
│       ├── ScrapingError
│       └── OllamaError
│
├── output/
│   ├── essay.md                     # Generated 750-word essay (Phase 2)
│   ├── traits.json                  # 5-20 traits with confidence + evidence (Phase 3)
│   ├── quiz_questions.json          # NEW: Posts tagged "quiz" saved here
│   ├── scraping_session.json        # NEW: Session state for resuming
│   └── [other outputs]
│
└── logs/
    ├── scraper.log                  # All application logs
    └── [debug logs]
```

## Key Components

### Phase 1: SCRAPING (Interactive)

**Flow:**
```
1. Authenticate with bdsmlr.com
2. Check for existing session
   └─ If exists: prompt user to resume
3. Discover blog URL (handles blog_name vs username)
4. Loop:
   └─ Fetch page
   └─ Parse posts
   └─ Add to session
   └─ Save session state
   └─ Prompt user: continue / stop / quit
5. Return: posts + session object
```

**Session Capabilities:**
- Resume from last position
- Avoid re-scraping duplicates
- Track page progress
- Auto-save after each decision

### Phase 2: SUMMARIZATION (AI)

**Flow:**
```
1. Deduplicate posts (by content hash)
2. Classify posts:
   ├─ text_clear → for essay generation
   ├─ image_dependent → skip
   └─ quiz_question → save to quiz_questions.json
3. Aggregate text_clear posts
4. Generate 750-word essay via Ollama
5. Save to output/essay.md
```

### Phase 3: TRAIT INFERENCE (AI)

**Flow:**
```
1. Read essay from Phase 2
2. Call Ollama with trait inference prompt
3. Extract 20 traits with:
   ├─ Name
   ├─ Confidence (0-100)
   ├─ Evidence excerpt
   └─ Direct quote from essay
4. Save to output/traits.json
```

## New Features in This Update

### ✅ Interactive Scraping
- `scrape_blog_interactive()` - User control during scraping
- Prompts after each page: continue / stop / quit
- Real-time post count display

### ✅ Session Persistence
- `ScrapingSession` dataclass - Track state
- `save_to_file()` / `load_from_file()` - JSON persistence
- Resume capability preserves all context

### ✅ Graceful Control
- Stop scraping without terminating app
- Offer analysis prompt before exit
- Save incomplete sessions for later

### ✅ Content Classification
- `_classify_content_type()` - Categorize posts
- text_clear: Relationship rules → trait inference
- image_dependent: Skip (no clear meaning)
- quiz_question: Reserve for Phase 2

### ✅ Quiz Question Extraction
- Automatically save posts tagged "quiz"
- Separate from trait analysis
- Ready for Phase 2 quiz development

## Configuration Options

```yaml
scraper:
  blog_name: "education.bdsmlr.com"
  interactive_scraping: true  # Enable user prompts
  request_delay: 2
  timeout: 30
  verify_ssl: false
  proxy:
    enabled: true
    url: "http://proxy:port"
```

## Output Files

### essay.md
Generated essay reflecting blog content and author personality

### traits.json
```json
{
  "traits": [
    {
      "name": "Emotional Expressiveness",
      "confidence": 85,
      "evidence": "The author discusses feelings...",
      "quote": "\"I believe in expressing...\"",
      "content_type": "text_clear"
    }
  ],
  "summary_reference": "essay.md",
  "generated_at": "2026-03-25T..."
}
```

### quiz_questions.json (NEW)
```json
{
  "quiz_questions": [
    {
      "post_id": "quiz_12345",
      "content": "Do you prefer...",
      "tags": ["quiz", "preference"],
      "content_type": "quiz_question"
    }
  ],
  "total_questions": 15,
  "saved_at": "2026-03-25T..."
}
```

### scraping_session.json (NEW)
Session state tracking for resume capability
