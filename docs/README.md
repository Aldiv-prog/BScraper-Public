# BScraper - Blog Content Extraction & AI Analysis Backend

Extract personal blog content from bdsmlr.com, generate AI-powered summaries, and infer personality traits.

## Project Status
**MVP Phase**: Scraping + Summarization + Trait Inference (backend only)

## Quick Start

### Prerequisites
- Python 3.8+
- Ollama installed and running (`ollama serve`)
- Ollama model: `gemma-3-4b-it-uncensored-v2-gguf:q5_k_m`

### Setup
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

### Configuration
```bash
# Copy template
cp config.example.yaml config.yaml

# Edit config.yaml with your settings (proxy, timeouts, etc.)
```

### Run Pipeline
```bash
python main.py
# Prompts: Enter bdsmlr.com username and password
# Outputs: essay.md and traits.json
```

### Test Components
```bash
python test_components.py
# Validates all imports and basic functionality
```

### Debug Scraping
```bash
python main.py --verbose --max-pages 1
# Test with first page only, detailed logging
```

## Pipeline Architecture

```
PHASE 1: SCRAPER       PHASE 2: SUMMARIZER       PHASE 3: TRAIT INFERENCE
Blog posts    →   Deduplicate    →   Raw text    →   Essay (750 words)    →   Traits (JSON)
(auth)            & aggregate       + tags           (Ollama)               (with evidence)
```

## Output Files

**essay.md** - Personal essay synthesizing blog themes (500-1000 words)

**traits.json** - Identified personality traits with:
- Trait name
- Confidence score (0-100)
- Evidence summary
- Direct quotes from essay

```json
{
  "traits": [
    {
      "name": "Dominance Orientation",
      "confidence": 87,
      "evidence": "The author frequently discusses leadership and decision-making",
      "quote": "\"I believe in taking control...\""
    }
  ],
  "total_identified": 15,
  "expected_total": 20,
  "generated_at": "2026-03-24T14:32:00"
}
```

## Configuration (config.yaml)

```yaml
scraper:
  base_url: "https://bdsmlr.com"
  request_delay: 2         # seconds between requests
  timeout: 10              # request timeout
  proxy:
    enabled: false
    url: "http://proxy:port"

summarizer:
  ollama_url: "http://localhost:11434"
  ollama_model: "gemma-3-4b-it-uncensored-v2-gguf:q5_k_m"
  timeout: 120

output:
  essay_word_count: 750    # target essay length
  essay_file: "output/essay.md"
  traits_file: "output/traits.json"

traits:
  total_count: 20
  base_traits:             # psychological traits (fixed)
    - "Dominance Orientation"
    - "Submission Orientation"
    # ... more
  custom_traits: []        # add your own (up to 10+)
```

## Debugging

### Enable Verbose Logging
```bash
python main.py --verbose
```

### Check Logs
- **Scraper**: `logs/scraper.log`
- **AI Engine**: `logs/ai_engine.log`

### Common Issues

**Ollama connection refused**
- Make sure Ollama is running: `ollama serve`
- Check `ollama_url` in config matches your setup

**Authentication fails**
- Verify bdsmlr.com username/password
- Check proxy settings if applicable

**Empty traits output**
- Ensure Ollama model is installed: `ollama pull gemma-3-4b-it-uncensored-v2-gguf:q5_k_m`
- Check `logs/ai_engine.log` for Ollama response errors
- Try increasing `timeout` in config if model is slow

## Scraper Implementation Details

### Authentication Flow
The scraper handles bdsmlr.com authentication with:
- **CSRF Token Extraction**: Automatically extracts CSRF tokens from login forms
- **Session Persistence**: Maintains authenticated sessions across requests
- **Browser Simulation**: Uses realistic headers to avoid detection
- **Error Handling**: Comprehensive error handling for auth failures

### Blog Scraping Strategy
- **URL Patterns**: Supports multiple blog URL formats (`/blog/username`, `/blog/username/page/N`)
- **Pagination Detection**: Automatically detects and follows pagination links
- **Content Validation**: Validates blog pages before parsing
- **Rate Limiting**: Respects configurable delays between requests

### HTML Parsing Flexibility
The scraper uses multiple fallback selectors for robust parsing:
- **Post Containers**: `article.post`, `div.entry`, `section.post`, etc.
- **Content Areas**: `div.content`, `div.post-content`, `p.content`, etc.
- **Tag Extraction**: Finds tags in various container formats
- **Date Parsing**: Supports ISO, US, and European date formats

### Error Recovery
- **Graceful Degradation**: Continues parsing even if some posts fail
- **Detailed Logging**: Logs parsing failures for debugging
- **Content Validation**: Skips posts with insufficient content
```
BScraper/
├── main.py                    # Entry point
├── config.example.yaml        # Configuration template
├── requirements.txt
├── scraper/                   # Blog scraping
│   ├── bdsmlr_scraper.py     # HTML parsing
│   ├── session_manager.py    # Authentication
│   └── models.py             # Data classes
├── processor/                 # Text processing
│   ├── deduplicator.py       # Remove duplicates
│   └── aggregator.py         # Combine posts
├── ai_engine/                 # AI analysis
│   ├── ollama_client.py      # Ollama API wrapper
│   ├── summarizer.py         # Essay generation
│   └── trait_extractor.py    # Personality analysis
├── utils/                     # Utilities
│   ├── config_loader.py      # YAML config
│   ├── logger.py             # Structured logging
│   └── exceptions.py         # Custom exceptions
└── output/                    # Generated files
    ├── essay.md              # Generated essay
    └── traits.json           # Generated traits
```

### Next Phase (Future)
- Web app for quiz generation and delivery
- User response storage and analytics
- Advanced image/GIF interpretation
- Custom trait management UI

## License
Private project

## Notes
- Never commit `config.yaml` (contains credentials)
- All network requests use configured proxy if enabled
- Ollama runs locally - no external API calls
- Trait inference works directly from raw blog content, not just the essay
