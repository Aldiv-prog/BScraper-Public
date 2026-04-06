# Configuration Parameter Reference

## Scraper Settings

### loading_indicator_timeout
**Type:** Integer (seconds)  
**Default:** 20  
**Range:** 5-120  
**Description:** Maximum seconds to wait for the site's loading indicator to disappear. If the indicator persists beyond this timeout, the scraper assumes end-of-blog has been reached.

**How it works:**
1. After scraping a page, scraper constructs the next page URL
2. Checks the next page for "loading" text indicator
3. Waits up to `loading_indicator_timeout` seconds for indicator to disappear
4. If indicator disappears → continue to next page
5. If timeout reached → stop scraping (end of blog detected)

**Recommended Values:**
- `10` - Fast networks, responsive servers, proxy is fast
- `20` - Standard networks, good for most cases (DEFAULT)
- `30` - Slow networks, heavily loaded servers
- `60` - Very slow networks, problematic proxies

**Example:**
```yaml
scraper:
  loading_indicator_timeout: 20
```

---

## Other Related Settings

### request_delay
**Type:** Integer (seconds)  
**Default:** 2  
**Description:** Delay between requests to avoid overwhelming the server

**Relationship to loading_indicator_timeout:**
- `request_delay` = minimum time between requests
- `loading_indicator_timeout` = maximum time to wait for page load
- These work together; `loading_indicator_timeout` should be ≥ `request_delay`

### timeout
**Type:** Integer (seconds)  
**Default:** 30  
**Description:** HTTP request timeout - max time to wait for server response

**Relationship to loading_indicator_timeout:**
- `timeout` = timeout for individual HTTP GET/POST
- `loading_indicator_timeout` = timeout for page loading indicator detection
- `timeout` should be less than `loading_indicator_timeout`

### interactive_scraping
**Type:** Boolean  
**Default:** true  
**Description:** Enable pause/resume control during scraping. Used alongside loading detection.

---

## Complete Scraper Configuration Example

```yaml
scraper:
  # Connection settings
  base_url: "https://bdsmlr.com"
  blog_name: "education.bdsmlr.com"
  request_delay: 2          # Wait 2 seconds between requests
  timeout: 30               # Individual request timeout
  verify_ssl: false         # SSL verification toggle
  
  # Interactive control
  interactive_scraping: true
  loading_indicator_timeout: 20  # NEW: Wait up to 20s for page load
  
  # Proxy (optional)
  proxy:
    enabled: true
    url: "http://192.168.0.132:3128"
```

---

## Tuning the Loading Timeout

### Step 1: Monitor Your Network
Run a single scrape and watch the logs:
```bash
python main.py --verbose
```

Look for entries like:
```
Still loading... (2s elapsed)
Still loading... (5s elapsed)
Page loaded after 7.2s
```

### Step 2: Calculate Timeout
- Add 5 seconds to the slowest page load time
- Example: If slowest page takes 12 seconds → set timeout to 17-20 seconds

### Step 3: Test
```yaml
scraper:
  loading_indicator_timeout: 20  # Your calculated value
```

Run again and verify:
- Pages load successfully
- End-of-blog is detected correctly
- No premature timeouts

### Step 4: Fine-Tune
- If timeouts too early: Increase by 5-10 seconds
- If hangs on loading: Decrease by 5 seconds  
- If works well: Leave as-is

---

## Diagnostic: Check Your Current Settings

Run this to see all current settings:
```python
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
    scraper_config = config.get('scraper', {})
    
    print(f"Request Delay: {scraper_config.get('request_delay')} seconds")
    print(f"HTTP Timeout: {scraper_config.get('timeout')} seconds")
    print(f"Loading Timeout: {scraper_config.get('loading_indicator_timeout', 20)} seconds")
    print(f"Interactive Mode: {scraper_config.get('interactive_scraping')} ")
```

---

## Common Configuration Issues

### Problem: Scraper stops too soon
**Likely cause:** `loading_indicator_timeout` is too short
**Solution:** Increase to 30-40 seconds
```yaml
scraper:
  loading_indicator_timeout: 30
```

### Problem: Scraper hangs waiting for page load
**Likely cause:** Server is slow or offline
**Check:** 
- Is the server up? Try accessing manually
- Is proxy working? Check `proxy.url` 
- Try increasing `request_delay` to 5 seconds

### Problem: Out of memory on large blogs
**Not related to loading_indicator_timeout**
**Solution:** Use session resume to scrape in batches

---

## Performance Notes

- Loading timeout adds ~1-2 seconds per page (checking loading status)
- Memory: No additional memory from loading detection
- Network: One extra GET request per page transition
- CPU: Minimal (just text searching and sleep)

---

## Summary Table

| Setting | Purpose | Related To | Typical Value |
|---------|---------|-----------|----------------|
| `loading_indicator_timeout` | Wait for page load | End-of-blog detection | 20s |
| `request_delay` | Min time between requests | Rate limiting | 2s |
| `timeout` | HTTP request max time | Network errors | 30s |
| `interactive_scraping` | Pause/resume control | User interaction | true |

**Rule of thumb:**
```
timeout < request_delay < loading_indicator_timeout
(e.g., 30s < 2s < 20s is wrong!)
Actually: timeout(30s) > request_delay(2s) 
And: loading_indicator_timeout(20s) independent
```

Wait, that's confusing. Let me clarify:
- `timeout`: Individual request max time (should be longest)
- `request_delay`: Minimum wait between requests
- `loading_indicator_timeout`: Max wait for page load indicator (checks every 1s)

Typical values work well:
- `timeout: 30`
- `request_delay: 2` 
- `loading_indicator_timeout: 20`

This means:
1. Make request (wait up to 30s for response)
2. Wait 2s before next request
3. For page load, wait up to 20s for loading to finish
