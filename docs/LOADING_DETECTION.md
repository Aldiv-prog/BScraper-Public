# Loading Indicator Detection & End-of-Blog Detection

## Problem
The scraper was terminating too early after page 1, without properly detecting when all pages had been scraped. The site displays a "loading" text indicator in the lower left corner while loading the next page, and this indicator persists (stays visible for more than 20 seconds) when the end of blog has been reached.

## Solution
Implemented comprehensive loading indicator detection with configurable timeout parameter. The scraper now:

1. **Detects Loading Indicator**: Looks for "loading", "loading...", or "please wait" text in the HTML
2. **Waits for Page Load**: Monitors the page and waits for the loading indicator to disappear
3. **Timeout Detection**: If loading persists beyond configured timeout (default 20s), concludes we've reached end of blog
4. **Graceful Stop**: Stops scraping and marks session as complete when timeout is reached

## Configuration

Add to `config.yaml`:

```yaml
scraper:
  # ... other settings ...
  loading_indicator_timeout: 20  # seconds to wait for loading indicator to disappear
```

**Parameters:**
- `loading_indicator_timeout`: Number of seconds to wait for loading indicator to disappear
  - Default: 20 seconds
  - Minimum recommended: 10 seconds
  - Maximum recommended: 60 seconds

## Implementation Details

### New Methods in BdsmlrScraper

#### 1. `_detect_loading_with_timeout(page_url: str) -> bool`
Waits for a page to load by detecting when the loading indicator disappears.

**Logic:**
- Fetches page at specified URL every 1 second
- Checks for "loading" text patterns in the page
- Returns `True` if loading completes within timeout
- Returns `False` if timeout reached (indicates end of blog)

**Used After:** User chooses to continue scraping to next page

#### 2. `_is_loading_persistent(html: str) -> bool`
Checks if loading indicator is persistent in HTML (indicates end of blog).

**Logic:**
- Searches HTML content for loading text patterns
- If found, waits and checks again at intervals
- Returns `True` if loading indicator remains after timeout
- Returns `False` if loading indicator disappeared

**Used:** As secondary check if primary detection fails

### Updated Scraping Loop

The main scraping loop (`_scrape_with_session_control`) now:

```python
# After parsing current page posts:
1. Extract next page URL
2. Call _detect_loading_with_timeout(next_page_url)
3. If timeout reached → mark session complete and stop
4. If page loaded → check for next page link
5. If next page exists → prompt user to continue
```

## Behavior

### Successful Pagination (Page Loads)
```
[Page 1] Current posts: 25
Page loaded after 3.2s
Scraped 25 posts so far.
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: c
[Page 2] Current posts: 50
```

### End of Blog (Loading Timeout)
```
[Page 1] Current posts: 25
Waiting for page to load (timeout: 20s)...
Still loading... (5s elapsed)
Still loading... (10s elapsed)
Still loading... (15s elapsed)
Loading timeout after 20s - likely end of blog
Loading timeout - reached end of blog
Session marked as complete
```

### User-Initiated Stop
```
[Page 1] Current posts: 25
Page loaded after 2.1s
Scraped 25 posts so far.
Options: (c)ontinue, (s)top & proceed with analysis, (q)uit: s
Stop & proceed with analysis? (y/n): y
```

## Loading Detection Patterns

The scraper searches for these text patterns:
- "loading" (case-insensitive)
- "loading..." (case-insensitive)  
- "please wait" (case-insensitive)

These patterns are checked in the full page text extracted by BeautifulSoup.

## Edge Cases Handled

1. **Network Error During Loading Check**: Waits 1 second and retries
2. **Multiple Check Intervals**: Only checks page every 1 second to avoid overload
3. **Partial Page Load**: Detects completion when loading indicator disappears
4. **Manual Stop**: User can press (s) to stop at any time regardless of loading status

## Performance Impact

- **Minimal Overhead**: Loading check occurs once per page transition
- **Polling Interval**: 1 second between checks (configurable internally)
- **Memory**: No additional memory required
- **Network**: One additional GET request per page to verify loading status

## Testing Recommendations

1. **Test Normal Pagination**: Run scraper and verify it continues through multiple pages
2. **Test End-of-Blog Detection**: Let scraper run until it reaches end and stops automatically
3. **Test Timeout Configuration**: 
   - Try with `loading_indicator_timeout: 10` for faster detection
   - Try with `loading_indicator_timeout: 30` for slower networks
4. **Test User Control**: Stop mid-scrape and verify session resumes correctly
5. **Test Resume**: After stopping, run again and verify it resumes from correct page

## Configuration Examples

### Fast Detection (10 seconds)
```yaml
scraper:
  loading_indicator_timeout: 10
```
Good for: Fast networks, responsive servers

### Default (20 seconds)
```yaml
scraper:
  loading_indicator_timeout: 20
```
Good for: Most use cases, balanced timeout

### Slow Network (60 seconds)
```yaml
scraper:
  loading_indicator_timeout: 60
```
Good for: Slow networks, heavily loaded servers, proxy delays

## Troubleshooting

### Scraper Stops Too Soon
- **Cause**: Timeout too short for network speed
- **Solution**: Increase `loading_indicator_timeout` to 30-60 seconds
- **Debug**: Check logs for "Loading timeout" messages

### Scraper Hangs on Loading Screen
- **Cause**: Site has new loading pattern not recognized
- **Solution**: Stop with (q) and report the pattern shown
- **Debug**: Check terminal for "Still loading..." messages

### Missing Pages
- **Cause**: Loading detection failed on a page transition
- **Solution**: Run with `--verbose` flag and check `logs/scraper.log`
- **Debug**: Look for "Waiting for page" entries and timeout values

## Files Modified

1. **config.yaml**
   - Added: `loading_indicator_timeout: 20`

2. **scraper/bdsmlr_scraper.py**
   - Updated: `__init__()` to accept `loading_timeout` parameter
   - Added: `_detect_loading_with_timeout()` method
   - Added: `_is_loading_persistent()` method
   - Updated: `_scrape_with_session_control()` to check loading before next page

3. **main.py**
   - Updated: BdsmlrScraper instantiation to pass `loading_timeout` from config
   - Added: Extraction of `loading_indicator_timeout` from config

## Future Enhancements

- [ ] Configurable loading detection patterns (regex in config)
- [ ] Adaptive timeout (learns network speed over time)
- [ ] Visual loading indicator in terminal
- [ ] HTTP status code monitoring (alternative to text detection)
- [ ] JavaScript rendering support (for SPA sites)
