# Interactive Scraping Guide

## Overview
BScraper now features interactive scraping with session persistence, allowing you to control the scraping process in real-time.

## Features

### 1. **Session Persistence**
- Scraping progress is automatically saved to `output/scraping_session.json`
- If scraping is interrupted, you can resume from the last position
- Each session tracks: posts scraped, current page, scroll depth, and completion status

### 2. **Interactive Control During Scraping**
After each page of posts is scraped, you'll see:
```
[Page 1] Current posts: 3

Options: (c)ontinue, (s)top & proceed with analysis, (q)uit:
```

**Options:**
- `c` - Continue scraping the next page
- `s` - Stop scraping and proceed directly to essay generation and trait inference
- `q` - Quit without saving (will not proceed with analysis)

### 3. **Session Resume**
When starting a new scraping run, if an incomplete session exists:
```
Found incomplete scraping session from 2026-03-25 06:45:05.
Previously scraped 45 posts.
Resume from last position? (y/n): 
```

- `y` - Resume from where you left off (posts are not re-scraped)
- `n` - Start a fresh session

### 4. **Graceful Analysis Prompt**
When you stop scraping early (using 's' option):
```
============================================================
Stopped scraping with 50 posts.
============================================================

Proceed with essay generation and trait inference? (y/n):
```

- `y` - Process the scraped posts and generate essay + traits
- `n` - Exit without processing (saves your session for later)

## Content Classification

Posts are automatically classified into three types:

1. **text_clear**: Explicit relationship/attitude rules
   - Used for trait inference
   - Must contain relationship keywords: want, expect, need, prefer, etc.

2. **image_dependent**: Short posts that rely on images for meaning
   - Skipped during analysis
   - Too short or no clear relationship content

3. **quiz_question**: Posts tagged with "quiz"
   - Saved to `output/quiz_questions.json`
   - Reserved for Phase 2 quiz development
   - Not used for trait inference

## Example Workflow

```bash
# Session 1: Scrape 50 posts then stop
python main.py
Enter bdsmlr.com username: alvil3@yahoo.com
Enter bdsmlr.com password: ****

[Page 1] Current posts: 10
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: c

[Page 2] Current posts: 25
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: c

[Page 3] Current posts: 50
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: s

============================================================
Stopped scraping with 50 posts.
============================================================

Proceed with essay generation and trait inference? (y/n): n
# Session saved to output/scraping_session.json
```

```bash
# Session 2: Resume and continue scraping
python main.py
Enter bdsmlr.com username: alvil3@yahoo.com
Enter bdsmlr.com password: ****

Found incomplete scraping session from 2026-03-25 06:45:05.
Previously scraped 50 posts.
Resume from last position? (y/n): y

[Page 4] Current posts: 75
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: c

[Page 5] Current posts: 100
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: s

============================================================
Stopped scraping with 100 posts.
============================================================

Proceed with essay generation and trait inference? (y/n): y
# Generates essay.md and traits.json
```

## Session File Format

Located at: `output/scraping_session.json`

```json
{
  "blog_name": "education.bdsmlr.com",
  "username": "alvil3@yahoo.com",
  "posts_scraped": [
    {
      "post_id": "post_12345",
      "title": "My expectations",
      "content": "I want a partner who...",
      "tags": ["relationship", "expectations"],
      "content_type": "text_clear",
      ...
    }
  ],
  "last_post_id": "post_12345",
  "current_page": 3,
  "total_scroll_depth": 0,
  "is_complete": false,
  "created_at": "2026-03-25T06:45:05",
  "last_updated": "2026-03-25T06:50:20"
}
```

## Configuration

Enable/disable interactive scraping in `config.yaml`:

```yaml
scraper:
  interactive_scraping: true  # Set to false to disable user prompts
```

## Important Notes

1. **Session Unique per Blog**: Each blog gets its own session tracking
2. **Automatic Deduplication**: Posts are tracked by ID to prevent duplicates when resuming
3. **Post Count**: Progress shows total scraped, not including duplicates
4. **No Partial Content**: Content filtering happens AFTER all scraping is complete
5. **Graceful Exit**: Pressing Ctrl+C during input will save your session
