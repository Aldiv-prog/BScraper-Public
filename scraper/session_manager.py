"""Session management for bdsmlr.com authentication."""

import re
import requests
import urllib3
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from utils.exceptions import AuthenticationError
from utils.logger import setup_logger

# Suppress SSL warnings when using proxy (expected for local proxy servers)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = setup_logger('scraper.session', 'logs/scraper.log')


class SessionManager:
    """Manages authenticated session with bdsmlr.com."""
    
    def __init__(
        self,
        base_url: str,
        proxy_url: Optional[str] = None,
        request_delay: float = 2,
        timeout: int = 10,
        verify_ssl: bool = True
    ):
        """
        Initialize session manager.
        
        Args:
            base_url: Base URL for bdsmlr.com
            proxy_url: Optional proxy URL
            request_delay: Delay between requests (seconds)
            timeout: Request timeout (seconds)
            verify_ssl: Whether to verify SSL/TLS certificates
        """
        self.base_url = base_url
        self.request_delay = request_delay
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        
        # Configure proxy if provided
        if proxy_url:
            self.session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            logger.info(f"Proxy configured: {proxy_url}")

        if not self.verify_ssl:
            self.session.verify = False
            logger.warning("SSL certificate verification is DISABLED (insecure)")
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate with bdsmlr.com.
        
        Args:
            username: bdsmlr.com username
            password: bdsmlr.com password
        
        Returns:
            True if authentication successful
        
        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            # First, get the login page to obtain any CSRF tokens or session cookies
            login_page_url = urljoin(self.base_url, '/login')
            logger.info("Fetching login page...")
            
            response = self.session.get(login_page_url, timeout=self.timeout)
            response.raise_for_status()
            
            # Debug: log form fields found
            soup = BeautifulSoup(response.text, 'html.parser')
            forms = soup.find_all('form')
            logger.debug(f"Found {len(forms)} forms on login page")
            
            for i, form in enumerate(forms):
                inputs = form.find_all('input')
                input_names = [inp.get('name') for inp in inputs if inp.get('name')]
                logger.debug(f"Form {i+1} inputs: {input_names}")
            
            # Extract CSRF token if present (common in modern web apps)
            csrf_token = self._extract_csrf_token(response.text)
            
            # Prepare login data
            login_data = {
                'email': username,  # bdsmlr.com uses 'email' field, not 'username'
                'password': password,
            }
            
            if csrf_token:
                login_data['_token'] = csrf_token  # bdsmlr.com uses '_token' field
                logger.debug("Using CSRF token for authentication")
            
            # Add common headers to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': login_page_url,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            logger.info(f"Attempting authentication for user: {username}")
            logger.debug(f"Login data keys: {list(login_data.keys())}")
            logger.debug(f"Login URL: {login_page_url}")
            
            logger.info(f"Attempting authentication for user: {username}")
            
            # Submit login form
            response = self.session.post(
                login_page_url,
                data=login_data,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False  # Don't follow redirects automatically
            )
            
            # Log response details for debugging
            logger.debug(f"Login response status: {response.status_code}")
            logger.debug(f"Login response URL: {response.url}")
            logger.debug(f"Login response content length: {len(response.text)}")
            
            # Handle redirects manually
            if response.status_code in [301, 302, 303, 307, 308]:
                redirect_url = response.headers.get('Location')
                logger.debug(f"Following redirect to: {redirect_url}")
                
                if redirect_url:
                    # Follow the redirect
                    response = self.session.get(
                        redirect_url if redirect_url.startswith('http') else urljoin(self.base_url, redirect_url),
                        timeout=self.timeout,
                        allow_redirects=True
                    )
                    logger.debug(f"Redirect response status: {response.status_code}")
                    logger.debug(f"Redirect response URL: {response.url}")
            
            # Check if authentication was successful
            if self._is_authenticated(response):
                logger.info(f"Successfully authenticated as {username}")
                return True
            else:
                # Log some response content for debugging
                content_preview = response.text[:500] + "..." if len(response.text) > 500 else response.text
                logger.debug(f"Login response content preview: {content_preview}")
                raise AuthenticationError(
                    f"Authentication failed: Invalid credentials or unexpected response"
                )
                
        except requests.RequestException as e:
            raise AuthenticationError(f"Authentication request failed: {e}")
    
    def _extract_csrf_token(self, html: str) -> Optional[str]:
        """
        Extract CSRF token from HTML.
        
        Args:
            html: HTML content
        
        Returns:
            CSRF token if found, None otherwise
        """
        # Common CSRF token patterns for bdsmlr.com and Laravel
        patterns = [
            r'name=["\']_token["\']\s+value=["\']([^"\']+)["\']',  # Laravel _token field
            r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']',  # Generic csrf_token
            r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',  # Meta tag
            r'csrf["\']:\s*["\']([^"\']+)["\']',  # JSON CSRF
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                token = match.group(1)
                logger.debug(f"Found CSRF token: {token[:10]}...")
                return token
        
        logger.debug("No CSRF token found")
        return None
    
    def _is_authenticated(self, response: requests.Response) -> bool:
        """
        Check if the response indicates successful authentication.
        
        Args:
            response: HTTP response after login attempt
        
        Returns:
            True if authenticated
        """
        # Log response details for debugging
        logger.debug(f"Login response status: {response.status_code}")
        logger.debug(f"Login response URL: {response.url}")
        logger.debug(f"Login response headers: {dict(response.headers)}")
        
        # Check for common success indicators
        if response.status_code in [200, 302, 301]:
            # Check if redirected to dashboard or blog
            final_url = response.url.lower()
            if any(path in final_url for path in ['dashboard', 'blog', 'home', 'account']):
                logger.debug("Authentication success: redirected to user area")
                return True
            
            # Check response content for success indicators
            content_lower = response.text.lower()
            
            # Positive indicators
            success_indicators = [
                'welcome', 'logout', 'my account', 'dashboard', 'profile',
                'settings', 'blog', 'post', 'create', 'edit'
            ]
            
            # Negative indicators (login page elements)
            failure_indicators = [
                'login', 'sign in', 'username', 'password', 'forgot password',
                'invalid credentials', 'error', 'incorrect'
            ]
            
            success_count = sum(1 for indicator in success_indicators if indicator in content_lower)
            failure_count = sum(1 for indicator in failure_indicators if indicator in content_lower)
            
            logger.debug(f"Success indicators: {success_count}, Failure indicators: {failure_count}")
            
            # If we have more success indicators than failure, consider it success
            if success_count > failure_count:
                logger.debug("Authentication success: content analysis")
                return True
            
            # Special case: if redirected and no login form visible
            if response.status_code in [302, 301] and 'login' not in content_lower:
                logger.debug("Authentication success: redirect without login form")
                return True
        
        logger.debug("Authentication failed: no success indicators found")
        return False
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Make authenticated GET request."""
        # Avoid duplicate 'timeout' parameter
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        if 'verify' not in kwargs:
            kwargs['verify'] = self.verify_ssl
        return self.session.get(url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """Make authenticated POST request."""
        # Avoid duplicate 'timeout' parameter
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        if 'verify' not in kwargs:
            kwargs['verify'] = self.verify_ssl
        return self.session.post(url, **kwargs)
    
    def close(self):
        """Close session."""
        self.session.close()
