# Interactive Scraping Flowchart

## Complete User Journey

```
START
  ↓
[Load Configuration]
  ↓
[Get Credentials]
  ↓
[Authenticate with bdsmlr.com]
  ├─ CSRF token extraction
  ├─ Email/password submission
  └─ Session cookie management
  ↓
[Discover Blog URL]
  ├─ Check if blog_name is full domain (education.bdsmlr.com)
  └─ Fallback to URL patterns if needed
  ↓
[Check for Existing Session] ◄─────────────────┐
  ├─ Session file exists?                      │
  │   ├─ Yes → Blog name matches?              │
  │   │   ├─ Yes → NOT complete?               │
  │   │   │   ├─ Yes → PROMPT: "Resume? (y/n)"
  │   │   │   │   ├─ y → Load posts + metadata
  │   │   │   │   │   └─ Continue from page N
  │   │   │   │   └─ n → New session
  │   │   │   └─ No → New session (marked complete)
  │   │   └─ No → New session (different blog)
  │   └─ No → New session
  ↓
[SCRAPING LOOP] ◄──────────────────────────────┐
  ├─ Fetch page                                │
  ├─ Parse posts                               │
  ├─ Classify each post:                       │
  │   ├─ Has "quiz" tag? → quiz_question       │
  │   ├─ < 20 chars? → image_dependent         │
  │   ├─ Has relationship keywords? → text_clear
  │   └─ Else → image_dependent                │
  ├─ Add non-duplicate posts to session        │
  ├─ Save session to JSON                      │
  ├─ Display: [Page N] Current posts: X        │
  ├─ PROMPT: "(c)ontinue, (s)top, (q)uit:"     │
  ├─ User input:                               │
  │   ├─ (c) → Next page (loop back)           │
  │   ├─ (s) → Break (graceful stop)           │
  │   └─ (q) → Raise KeyboardInterrupt         │
  ├─ More pages?                               │
  │   ├─ Yes → (loop back)                     │
  │   └─ No → Mark session.is_complete = True  │
  ↓
[Post-Scraping Decision]
  ├─ Session marked complete?
  │   ├─ Yes → Proceed to dedup/aggregate
  │   └─ No → PROMPT: "Proceed with analysis? (y/n)"
  │       ├─ y → Proceed to dedup/aggregate
  │       └─ n → EXIT (session saved)
  ↓
[PHASE 2: SUMMARIZATION]
  ├─ Deduplicate posts (SHA256 hash)
  ├─ Separate by content_type:
  │   ├─ text_clear → Use for essay
  │   ├─ image_dependent → Skip
  │   └─ quiz_question → Save to quiz_questions.json
  ├─ Aggregate text_clear posts
  ├─ Call Ollama with essay prompt
  ├─ Save essay to output/essay.md
  ↓
[PHASE 3: TRAIT INFERENCE]
  ├─ Read essay.md
  ├─ Call Ollama with trait extraction prompt
  ├─ Parse response (JSON)
  ├─ Extract 20 traits with evidence
  ├─ Filter by confidence threshold (50%)
  ├─ Save to output/traits.json
  ↓
[DISPLAY SUMMARY]
  ├─ ✓ Scraped X unique posts
  ├─ ✓ Generated 750-word essay
  ├─ ✓ Identified Y personality traits
  ├─ Output: output/essay.md
  ├─ Output: output/traits.json
  ├─ Output: output/quiz_questions.json
  ↓
EXIT (Success)
```

## Error Handling Paths

```
[Authentication Failed]
  └─ Raise AuthenticationError
  └─ EXIT

[Network Error During Scraping]
  └─ Session auto-saved
  └─ User can retry (will resume)

[Invalid Blog URL]
  └─ Try alternative patterns
  └─ If all fail: Raise ScrapingError

[Ctrl+C / KeyboardInterrupt]
  └─ Save current session
  └─ EXIT gracefully

[Ollama Connection Failed]
  └─ Raise OllamaError
  └─ EXIT (suggest checking ollama serve)

[JSON Parsing Error (Ollama response)]
  └─ Log error
  └─ Fallback to empty traits
  └─ Continue

[Corrupted Session File]
  └─ Skip loading
  └─ Start fresh session
```

## Session State Transitions

```
                    START
                     ↓
            [New Session Created]
                     ↓
        ┌────────────┴────────────┐
        │                         │
        v                         v
  [Active/Scraping]        [Loading Previous]
        │                         │
        │                         v
        │                   [Found Valid?]
        │                    Yes  │  No
        │                    │    └─→ [New Session]
        │                    v
        │              [Resume Selected?]
        │                Y    │    N
        │                │    └────→ [New Session]
        │                v
        │           [Resumed Session]
        │                     │
        └─────────────────────┘
                    ↓
            [Scraping Loop]
                    ↓
        ┌───────────┬───────────┬───────────┐
        │           │           │           │
        v           v           v           v
      (c)ontinue  (s)top      (q)uit    [No More Posts]
        │           │           │           │
        v           v           v           v
     [Resume]  [Save+Pause]  [Exit!]   [Complete!]
               [Analysis?]
                  Y  │  N
                  │  └─→ [EXIT]
                  v
            [Processing]
                  ↓
            [Complete!]
```

## Session Persistence Lifecycle

```
1. SESSION CREATION
   - New or Load from file
   - Set: blog_name, username, created_at
   - Init: posts_scraped = []

2. SESSION DURING SCRAPING
   - Each page: posts_scraped.append(post_dict)
   - Each decision: save_to_file()
   - Update: last_post_id, current_page, last_updated

3. SESSION COMPLETION
   - Set: is_complete = True
   - Final save_to_file()
   - Delete/archive session file (optional)

4. SESSION RECOVERY
   - Load file → ScrapingSession object
   - Check: blog_name, is_complete
   - Restore: posts_scraped list
   - Continue from: current_page

5. SESSION FILE
   Location: output/scraping_session.json
   Format: JSON (human-readable, editable)
   Size: Small (~10KB per 100 posts)
   Lifecycle: Auto-saved, persists until completion
```

## Content Type Classification Tree

```
Post Content
    │
    ├─ Tagged "quiz"?
    │   └─ YES → quiz_question ✓
    │
    ├─ < 20 characters?
    │   └─ YES → image_dependent (too short)
    │
    ├─ >= 1 sentence?
    │   ├─ NO → image_dependent (fragments)
    │   │
    │   └─ YES
    │       ├─ Contains relationship keywords? (want, expect, etc)
    │       │   └─ >= 2 found → text_clear ✓
    │       │
    │       ├─ Contains rule keywords? (rule, expectation, requirement)
    │       │   └─ YES → text_clear ✓
    │       │
    │       ├─ Contains preference phrases? ("i want", "i expect", etc)
    │       │   └─ YES → text_clear ✓
    │       │
    │       └─ ELSE → image_dependent (unclear)
```

## Output Generation

```
Scraped Posts
    ↓
[Deduplicator]
    ├─ Hash each post content
    └─ Remove duplicates
    ↓
Unique Posts
    ↓
[Content Classifier]
    ├─ text_clear  ──→ [Aggregator] ──→ [Essay Generator] ──→ output/essay.md
    ├─ quiz        ──→ [Saver] ──→ output/quiz_questions.json
    └─ image_dependent ──→ [Skip]
    ↓
Aggregated Content
    ↓
[Essay via Ollama]
    └─→ output/essay.md
    ↓
[Trait Extractor via Ollama]
    └─→ output/traits.json
```
