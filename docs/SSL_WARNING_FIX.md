# SSL Warning Fix

## Problem
Getting `InsecureRequestWarning` about unverified HTTPS requests to proxy host '192.168.0.132'.

## Root Cause
The config has `verify_ssl: false` which disables SSL certificate verification for all requests, including proxy connections. The proxy server at `192.168.0.132:3128` uses HTTPS, so urllib3 warns about the unverified connection.

## Solution
Added urllib3 warning suppression in `scraper/session_manager.py`:

```python
import urllib3
# Suppress SSL warnings when using proxy (expected for local proxy servers)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

## Why This Fix
- **Expected Behavior**: Local proxy servers often use self-signed certificates
- **Safe**: Only suppresses the warning, doesn't change security behavior
- **Targeted**: Only affects InsecureRequestWarning, not other warnings
- **Maintains Functionality**: SSL verification remains disabled as configured

## Alternative Solutions (Not Used)
1. **Enable SSL verification**: Would require valid certificates on proxy
2. **Use HTTP proxy**: Change proxy to use HTTP instead of HTTPS
3. **Custom warning filter**: More complex than needed

## Testing
Run the scraper and verify no SSL warnings appear:
```bash
python main.py
```

The warning should no longer appear during proxy connections.