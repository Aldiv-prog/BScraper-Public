"""BDSMLR blog scraper."""

import re
import time
import requests
from typing import List, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scraper.models import BlogPost, ScrapingSession
from scraper.session_manager import SessionManager
from utils.exceptions import ScrapingError
from utils.logger import setup_logger

logger = setup_logger('scraper.bdsmlr', 'logs/scraper.log')


class BdsmlrScraper:
    """Scrapes blog content from bdsmlr.com with interactive session control."""
    
    def __init__(self, session_manager: SessionManager, session_file: str = "output/scraping_session.json"):
        self.session = session_manager
        self.base_url = session_manager.base_url
        self.session_file = session_file
    
    def scrape_blog_interactive(self, blog_name: str, username: str, auto_resume: bool = False) -> Tuple[List[BlogPost], ScrapingSession]:
        """
        Scrape blog with interactive control and session management.
        
        Args:
            blog_name: Blog name/domain to scrape
            username: Username for session tracking
            auto_resume: If True, automatically resume a saved session without prompts
        
        Returns:
            Tuple of (posts list, session object)
        
        Raises:
            ScrapingError: If scraping fails
        """
        # Try to load previous session
        existing_session = ScrapingSession.load_from_file(self.session_file)
        
        if existing_session and existing_session.blog_name == blog_name:
            status = "incomplete" if not existing_session.is_complete else "complete"
            if auto_resume:
                logger.info(f"Auto-resume enabled: loading existing {status} session with {len(existing_session.posts_scraped)} posts")
                if existing_session.is_complete:
                    return [self._dict_to_blogpost(p) for p in existing_session.posts_scraped], existing_session
                existing_session.is_complete = False
                return self._scrape_with_session_control(blog_name, existing_session)

            response = input(
                f"\nFound {status} scraping session from {existing_session.last_updated}.\n"
                f"Previously scraped {len(existing_session.posts_scraped)} posts.\n"
                "Resume from this session? (y/n): "
            )
            
            if response.lower() == 'y':
                if existing_session.is_complete:
                    logger.info(f"Using completed saved session with {len(existing_session.posts_scraped)} posts")
                    return [self._dict_to_blogpost(p) for p in existing_session.posts_scraped], existing_session
                logger.info(f"Resuming session with {len(existing_session.posts_scraped)} posts")
                existing_session.is_complete = False
                return self._scrape_with_session_control(blog_name, existing_session)
            else:
                logger.info("User chose not to resume; starting fresh session")
        
        # Start new session
        session = ScrapingSession(
            blog_name=blog_name,
            username=username,
            posts_scraped=[],
            created_at=datetime.now()
        )
        
        return self._scrape_with_session_control(blog_name, session)
    
    def _scrape_with_session_control(self, blog_name: str, session: ScrapingSession) -> Tuple[List[BlogPost], ScrapingSession]:
        """
        Scrape with interactive session control using infinite scroll behavior.
        Stays on the same URL and pulls data from sideblog endpoints when available.

        Args:
            blog_name: Blog name to scrape
            session: Existing or new session object

        Returns:
            Tuple of (posts list, updated session)
        """
        try:
            blog_url = self._discover_blog_url(blog_name)
            logger.info(f"Using blog URL: {blog_url}")

            # Load initial page to compute blogid and verify the blog exists
            initial_response = self.session.get(blog_url)
            initial_response.raise_for_status()

            blogid = self._extract_blog_id(initial_response.text, blog_url)
            if not blogid:
                if self.blog_name.endswith('.bdsmlr.com'):
                    blogid = self.blog_name
                    logger.info(f"Using blog name as blogid for bdsmlr subdomain: {blogid}")
                else:
                    logger.warning("Could not extract blog ID from page; falling back to static content parsing")
            else:
                logger.info(f"Extracted blogid: {blogid}")

            # If we can use sideblog endpoints, do that (JS-free path)
            if blogid:
                logger.info(f"Using sideblog endpoint for blogid={blogid}")
                current_payload_lastpost = session.last_post_id
                scroll_attempt = session.current_page

                retry_count = 0
                max_retries = 3

                while True:
                    logger.info(f"Scroll attempt {scroll_attempt} using sideblog (lastpost={current_payload_lastpost})")
                    print(f"\n[Scroll {scroll_attempt}] Current posts: {len(session.posts_scraped)}")

                    try:
                        ajax_html = self._fetch_sideblog_html(blogid, lastpost=current_payload_lastpost, referer_url=blog_url)
                    except KeyboardInterrupt:
                        logger.info("Scraping interrupted by user")
                        break

                    logger.debug(f"AJAX response length: {len(ajax_html)}")
                    logger.debug(f"AJAX response preview: {ajax_html[:500]}...")

                    page_posts = self._parse_posts(ajax_html, blog_url)

                    logger.debug(f"Parsed {len(page_posts)} posts from AJAX response")

                    if not page_posts:
                        logger.info(f"No posts found on scroll attempt {scroll_attempt}.")

                        # Retry with longer wait before giving up
                        if retry_count < max_retries:
                            retry_count += 1
                            logger.info(f"Retrying fetch (attempt {retry_count}/{max_retries}) after 15s wait...")
                            time.sleep(15)  # Wait 15 seconds before retry
                            continue

                        logger.info("No posts found after retries - reached end of blog")
                        session.is_complete = True
                        break

                    retry_count = 0

                    # Count new posts added
                    new_posts_count = 0
                    for post in page_posts:
                        if post.post_id not in [p['post_id'] for p in session.posts_scraped]:
                            session.posts_scraped.append(post.to_dict())
                            session.last_post_id = post.post_id
                            new_posts_count += 1

                    logger.info(f"Added {new_posts_count} new posts. Total: {len(session.posts_scraped)}")

                    if new_posts_count == 0:
                        logger.info("No new posts found - reached end of sideblog stream")
                        session.is_complete = True
                        break

                    # Update for next cycle
                    current_payload_lastpost = session.last_post_id
                    scroll_attempt += 1
                    session.current_page = scroll_attempt
                    session.save_to_file(self.session_file)

                    time.sleep(self.session.request_delay)

                logger.info(f"Scraping complete. Total posts: {len(session.posts_scraped)}")
                session.save_to_file(self.session_file)
                return [self._dict_to_blogpost(p) for p in session.posts_scraped], session

            # Fallback to standard blog page parsing with pagination
            current_url = blog_url
            scroll_attempt = session.current_page

            while True:
                logger.info(f"Scroll attempt {scroll_attempt}...")
                print(f"\n[Scroll {scroll_attempt}] Current posts: {len(session.posts_scraped)}")

                try:
                    response = self.session.get(current_url)
                except KeyboardInterrupt:
                    logger.info("Scraping interrupted by user")
                    break
                response.raise_for_status()

                # Debug: Log session details
                logger.debug(f"Request URL: {response.url}")
                logger.debug(f"Response status: {response.status_code}")
                logger.debug(f"Session cookies: {list(self.session.session.cookies.get_dict().keys())}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                logger.debug(f"Blog page content length: {len(response.text)}")
                logger.debug(f"Blog page content preview: {response.text[:1000]}...")
                
                if not self._is_blog_page(response.text):
                    logger.warning(f"URL doesn't appear to be a valid blog page")
                    break

                page_posts = self._parse_posts(response.text, current_url)

                if not page_posts:
                    logger.info(f"No posts found on page {scroll_attempt}.")

                    logger.info("No posts found - reached end of blog")
                    session.is_complete = True
                    break

                # Count new posts added
                new_posts_count = 0
                for post in page_posts:
                    if post.post_id not in [p['post_id'] for p in session.posts_scraped]:
                        session.posts_scraped.append(post.to_dict())
                        session.last_post_id = post.post_id
                        new_posts_count += 1

                logger.info(f"Added {new_posts_count} new posts. Total: {len(session.posts_scraped)}")

                # If no new posts were added, check if we should retry
                if new_posts_count == 0:
                    # Allow up to 3 attempts before giving up
                    if scroll_attempt >= 3:
                        logger.info("No new posts found after multiple pages - reached end of blog")
                        session.is_complete = True
                        break
                    else:
                        logger.info(f"No new posts on page {scroll_attempt}; trying next page")
                        scroll_attempt += 1
                        current_url = f"{blog_url.rstrip('/')}/page/{scroll_attempt}"
                        continue

                # Move to next page
                scroll_attempt += 1
                current_url = f"{blog_url.rstrip('/')}/page/{scroll_attempt}"
                session.current_page = scroll_attempt
                session.save_to_file(self.session_file)

                time.sleep(self.session.request_delay)

            logger.info(f"Scraping complete. Total posts: {len(session.posts_scraped)}")
            session.save_to_file(self.session_file)

            return [self._dict_to_blogpost(p) for p in session.posts_scraped], session

        except Exception as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            raise ScrapingError(f"Failed to scrape blog: {e}")
    
    def _verify_authentication(self) -> bool:
        """
        Verify that the session is properly authenticated.
        
        Returns:
            True if authenticated, False otherwise
        """
        try:
            response = self.session.get(self.base_url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                page_text = response.text.lower()
                
                # Look for multiple signs of being logged in
                auth_indicators = [
                    # Logout links
                    soup.find('a', text=re.compile(r'logout|sign out', re.I)),
                    soup.find('a', href=re.compile(r'logout|sign.?out', re.I)),
                    
                    # User menu/profile elements
                    soup.find('div', class_=re.compile(r'user.*menu|profile.*menu', re.I)),
                    soup.find('span', class_=re.compile(r'username|user.*name', re.I)),
                    soup.find('a', href=re.compile(r'profile|account|settings', re.I)),
                    
                    # Dashboard or user-specific content
                    soup.find('a', href=re.compile(r'dashboard', re.I)),
                    soup.find(text=re.compile(r'welcome|hello', re.I)),
                    
                    # Check for absence of login form
                    not soup.find('form', action=re.compile(r'login', re.I)),
                    
                    # Check for specific cookies or session data
                    'blogs=' in str(self.session.session.cookies.get_dict()) if self.session.session.cookies else False
                ]
                
                # Count positive indicators
                positive_indicators = sum(1 for indicator in auth_indicators if indicator)
                
                if positive_indicators >= 2:  # Require at least 2 indicators
                    logger.debug(f"Authentication verified - found {positive_indicators} positive indicators")
                    return True
                else:
                    logger.warning(f"Authentication check failed - only {positive_indicators} positive indicators found")
                    logger.debug(f"Page title: {soup.title.text if soup.title else 'No title'}")
                    logger.debug(f"Looking for logout links: {bool(soup.find('a', text=re.compile(r'logout', re.I)))}")
                    logger.debug(f"Has blogs cookie: {'blogs=' in str(self.session.cookies.get_dict()) if self.session.cookies else False}")
                    
                    # Debug: Show some page content
                    logger.debug(f"Page content preview: {page_text[:500]}...")
                    return False
            else:
                logger.warning(f"Authentication check failed - homepage returned status {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Authentication check failed with exception: {e}")
            return False
    
    def _discover_blog_url(self, blog_name: str) -> str:
        """
        Discover the correct blog URL for the user.
        
        Args:
            blog_name: Blog name (can be username or full domain like education.bdsmlr.com)
        
        Returns:
            Correct blog URL
        
        Raises:
            ScrapingError: If blog URL cannot be discovered
        """
        logger.info(f"Attempting to discover blog URL for: {blog_name}")
        
        # First verify authentication is working
        if not self._verify_authentication():
            logger.warning("Authentication may not be working properly - this could affect blog access")
        
        # If blog_name looks like a full domain, use it directly
        if '.' in blog_name and 'bdsmlr.com' in blog_name:
            blog_url = f"https://{blog_name}"
            if not blog_url.endswith('/'):
                blog_url += '/'
            
            logger.debug(f"Using full domain blog URL: {blog_url}")
            
            try:
                response = self.session.get(blog_url)
                logger.debug(f"Response status: {response.status_code}")
                logger.debug(f"Response URL after redirects: {response.url}")
                
                # Check if we got redirected to login (sign of bad auth)
                if 'login' in response.url.lower():
                    logger.warning(f"Blog URL {blog_url} redirected to login - may need to re-authenticate")
                else:
                    # Check for blogid (JS sideblog endpoint) before flagging private
                    blogid = self._extract_blog_id(response.text, blog_url)
                    if blogid:
                        logger.info(f"Found blogid {blogid} on first load, accepting {blog_url} for scraping")
                        return blog_url

                    # Check if this is a private/placeholder page
                    page_text = response.text.lower()
                    if any(phrase in page_text for phrase in [
                        "nothing here yet",
                        "this user has no posts",
                        "private blog",
                        "login required"
                    ]):
                        logger.warning(f"Blog URL {blog_url} appears to be private or empty")

                    if response.status_code == 200 and self._is_blog_page(response.text):
                        logger.info(f"Found working blog URL: {blog_url}")
                        return blog_url
                    else:
                        logger.debug(f"Full domain URL {blog_url} returned status {response.status_code}")
            except Exception as e:
                logger.debug(f"Full domain URL {blog_url} failed: {e}")
        
        # First, check the homepage after authentication to see if there are blog links
        try:
            logger.debug("Checking homepage for blog links...")
            response = self.session.get(self.base_url)
            if response.status_code == 200:
                homepage_soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for links to the blog
                blog_links = []
                for link in homepage_soup.find_all('a', href=True):
                    href = link['href']
                    if blog_name.lower() in href.lower() and ('blog' in href or '@' in href or 'bdsmlr.com' in href):
                        blog_links.append(urljoin(self.base_url, href))
                
                if blog_links:
                    logger.info(f"Found potential blog links on homepage: {blog_links}")
                    # Try the first one
                    blog_url = blog_links[0]
                    logger.debug(f"Trying homepage blog link: {blog_url}")
                    response = self.session.get(blog_url)
                    if response.status_code == 200 and self._is_blog_page(response.text):
                        logger.info(f"Found working blog URL from homepage: {blog_url}")
                        return blog_url
        
        except Exception as e:
            logger.debug(f"Homepage check failed: {e}")
        
        # Try different blog URL patterns using the blog_name
        url_patterns = [
            f"/blog/{blog_name}",
            f"/@{blog_name}",
            f"/users/{blog_name}",
            f"/u/{blog_name}",
            f"/{blog_name}",  # Simple blog name path
        ]
        
        for pattern in url_patterns:
            blog_url = urljoin(self.base_url, pattern)
            logger.debug(f"Trying blog URL: {blog_url}")
            
            try:
                response = self.session.get(blog_url)
                logger.debug(f"Response status: {response.status_code}")
                
                # Attempt to detect blogid even if the page looks private/placeholder
                blogid = self._extract_blog_id(response.text, blog_url)
                if blogid:
                    logger.info(f"Found blogid {blogid} on URL {blog_url}, accepting {blog_url} for scraping")
                    return blog_url

                # Check for private/placeholder content
                page_text = response.text.lower()
                if any(phrase in page_text for phrase in [
                    "nothing here yet",
                    "this user has no posts",
                    "private blog", 
                    "login required"
                ]):
                    logger.warning(f"Pattern {pattern} returned private/placeholder page content")
                    continue
                
                # If we get a successful response and it looks like a blog page
                if response.status_code == 200 and self._is_blog_page(response.text):
                    logger.info(f"Found working blog URL: {blog_url}")
                    return blog_url
                elif response.status_code == 410:
                    logger.debug(f"URL {blog_url} returned 410 Gone")
                elif response.status_code == 404:
                    logger.debug(f"URL {blog_url} returned 404 Not Found")
                else:
                    logger.debug(f"URL {blog_url} returned status {response.status_code}")
                    
            except Exception as e:
                logger.debug(f"URL {blog_url} failed: {e}")
                continue
        
        # If no pattern works, raise an error
        raise ScrapingError(
            f"Could not find blog for '{blog_name}'. "
            "Please verify the blog name and that the blog exists."
        )

    def _extract_blog_id(self, html: str, blog_url: str = "") -> Optional[str]:
        """Extract sideblog blog ID from page HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        # Most pages include <div class="blogid" data-id="12345"></div>
        blogid_elem = soup.find('div', class_='blogid')
        if blogid_elem and blogid_elem.get('data-id'):
            return str(blogid_elem['data-id']).strip()

        # Fallback: regex search
        match = re.search(r'/sideblog/(\d+)', html)
        if match:
            return match.group(1)

        match = re.search(r'data-id=["\'](\d+)["\']', html)
        if match:
            return match.group(1)

        # Additional patterns
        match = re.search(r'blogid\s*[:=]\s*["\']?(\d+)["\']?', html, re.IGNORECASE)
        if match:
            return match.group(1)

        match = re.search(r'blog_id\s*[:=]\s*["\']?(\d+)["\']?', html, re.IGNORECASE)
        if match:
            return match.group(1)

        # Look for blogid in meta tags
        blogid_meta = soup.find('meta', attrs={'name': re.compile('blogid', re.IGNORECASE)})
        if blogid_meta and blogid_meta.get('content'):
            return str(blogid_meta['content']).strip()

        # Fallback: use the netloc if it's a subdomain
        if blog_url:
            from urllib.parse import urlparse
            parsed = urlparse(blog_url)
            if parsed.netloc != 'bdsmlr.com' and '.' in parsed.netloc:
                return parsed.netloc

        return None

    def _normalize_lastpost_id(self, lastpost: Optional[str]) -> Optional[str]:
        """Normalize lastpost ID for sideblog/infiniteside requests."""
        if not lastpost:
            return None

        # BDSMLR sideblog expects numeric ID not internal prefixed id in some cases
        normalized = str(lastpost).strip()
        if normalized.startswith('post_'):
            normalized = normalized[len('post_'):]
        return normalized

    def _extract_csrf_token(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML or session cookies."""
        soup = BeautifulSoup(html, 'html.parser')
        meta = soup.find('meta', attrs={'name': 'csrf-token'})
        if meta and meta.get('content'):
            return meta.get('content')

        # Try reading from cookies
        token = self.session.session.cookies.get('XSRF-TOKEN')
        if token:
            # token may be URL encoded
            return requests.utils.unquote(token)

        # Keep previous implementation in SessionManager is also useful
        return None

    def _fetch_sideblog_html(self, blogid: str, lastpost: Optional[str] = None, referer_url: Optional[str] = None) -> str:
        """Fetch sideblog content via AJAX endpoints."""
        if lastpost:
            endpoint = f"/infiniteside/{blogid}"
            normalized_lastpost = self._normalize_lastpost_id(lastpost)
            payload = {'blogid': blogid, 'lastpost': normalized_lastpost}
        else:
            endpoint = f"/sideblog/{blogid}"
            payload = {'blogid': blogid}

        url = urljoin(self.base_url, endpoint)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.base_url,
            'Referer': referer_url or self.base_url,
        }

        # fetch CSRF token from the referer page (or base page) if available
        page_for_token_url = referer_url or self.base_url
        try:
            token_page = self.session.get(page_for_token_url)
            token = self._extract_csrf_token(token_page.text)
        except Exception:
            token = None

        if not token:
            token = self.session.session.cookies.get('XSRF-TOKEN')
            if token:
                token = requests.utils.unquote(token)

        if token:
            headers['X-CSRF-TOKEN'] = token

        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'

        logger.debug(f"Fetching sideblog URL {url} with payload {payload} and headers {headers}")
        response = self.session.post(url, data=payload, headers=headers)
        response.raise_for_status()

        return response.text

    def _construct_page_url(self, base_blog_url: str, page: int) -> str:
        """
        Construct the URL for a specific page.
        
        Args:
            base_blog_url: Base blog URL
            page: Page number
        
        Returns:
            Full URL for the page
        """
        if page == 1:
            return base_blog_url
        else:
            # Try different pagination patterns
            patterns = [
                f"{base_blog_url}/page/{page}",
                f"{base_blog_url}?page={page}",
                f"{base_blog_url}/p/{page}",
            ]
            
            # For now, use the most common pattern
            return patterns[0]
    
    def _is_blog_page(self, html: str) -> bool:
        """
        Check if the HTML represents a valid blog page.
        
        Args:
            html: HTML content
        
        Returns:
            True if this appears to be a blog page
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for "no posts" or private blog indicators
        page_text = soup.get_text().lower()

        # Explicit sideblog marker overrides idioms in page text
        if soup.find('div', class_='sidepostcontainer') or soup.find('div', class_='postholder'):
            return True

        if any(phrase in page_text for phrase in [
            "nothing here yet",
            "this user has no posts",
            "perhaps in the future",
            "private blog",
            "this blog is private",
            "access denied",
            "login required"
        ]):
            logger.warning("Page appears to be a private/empty blog page")
            return False
        
        # Check for common blog page indicators and generic content markers
        blog_indicators = [
            soup.find('div', class_=re.compile(r'blog|posts|content')),
            soup.find('article', class_=re.compile(r'post')),
            soup.find_all('h2', class_=re.compile(r'post-title|title')),
            soup.find('div', id=re.compile(r'blog|posts')),
        ]
        
        return any(indicator for indicator in blog_indicators)
    
    def _has_next_page(self, html: str) -> bool:
        """
        Check if there's a next page link.
        
        Args:
            html: HTML content
        
        Returns:
            True if next page exists
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for pagination links
        next_link = soup.find('a', string=re.compile(r'next|older|>', re.IGNORECASE))
        if next_link:
            return True
        
        # Look for pagination classes
        pagination = soup.find('div', class_=re.compile(r'pagination|pager'))
        if pagination:
            next_buttons = pagination.find_all('a', class_=re.compile(r'next|older'))
            if next_buttons:
                return True
        
        return False
    
    def _parse_posts(self, html: str, base_url: str) -> List[BlogPost]:
        """
        Parse blog posts from HTML.
        
        Args:
            html: HTML content
            base_url: Base URL for relative links
        
        Returns:
            List of parsed BlogPost objects
        """
        posts = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try multiple selectors for different blog layouts
        post_selectors = [
            ('div', {'class': 'postholder'}),
            ('article', {'class': re.compile(r'post|entry')}),
            ('div', {'class': re.compile(r'post|entry|blog-post')}),
            ('section', {'class': re.compile(r'post|entry')}),
            ('li', {'class': re.compile(r'post|entry')}),
        ]
        
        post_elements = []
        for tag, attrs in post_selectors:
            elements = soup.find_all(tag, attrs)
            if elements:
                post_elements = elements
                logger.debug(f"Found {len(elements)} posts using selector: {tag}.{attrs}")
                break
        
        # If no posts found with standard selectors, try broader search
        if not post_elements:
            logger.debug("No posts found with standard selectors, trying broader search...")
            
            # Look for any elements that might contain posts
            potential_post_containers = [
                soup.find_all('div', class_=re.compile(r'content|main|blog')),
                soup.find_all('article'),
                soup.find_all('section'),
                soup.find_all('div', id=re.compile(r'content|main|posts')),
            ]
            
            for container_list in potential_post_containers:
                if container_list:
                    logger.debug(f"Found {len(container_list)} potential containers")
                    # Take the first one that has substantial content
                    for container in container_list:
                        text_content = container.get_text().strip()
                        if len(text_content) > 100:  # Substantial content
                            logger.debug(f"Container has {len(text_content)} characters of content")
                            # Try to find post-like elements within this container
                            inner_posts = container.find_all(['div', 'article', 'section'], class_=re.compile(r'.*'))
                            if inner_posts:
                                logger.debug(f"Found {len(inner_posts)} potential post elements in container")
                                post_elements = inner_posts
                                break
                    if post_elements:
                        break
        
        if not post_elements:
            logger.warning("No post elements found with standard selectors")
            # Debug: Show some page structure
            logger.debug(f"Page title: {soup.title.text if soup.title else 'No title'}")
            logger.debug(f"Body content length: {len(soup.body.get_text()) if soup.body else 0}")
            return posts
        
        for post_elem in post_elements:
            try:
                post_data = self._extract_post_data(post_elem, base_url)
                if post_data:
                    posts.append(post_data)
                
            except Exception as e:
                logger.warning(f"Failed to parse post element: {e}")
                continue
        
        return posts
    
    def _extract_post_data(self, post_elem, base_url: str) -> Optional[BlogPost]:
        """
        Extract data from a single post element.
        
        Args:
            post_elem: BeautifulSoup element
            base_url: Base URL for relative links
        
        Returns:
            BlogPost object or None if extraction fails
        """
        try:
            # Extract post ID from footer element (most reliable)
            footer = post_elem.find('div', class_='footer')
            post_id = None
            if footer:
                post_id = footer.get('data-id', '')
            
            # Fallback to element attributes
            if not post_id:
                post_id = (
                    post_elem.get('id', '') or
                    post_elem.get('data-id', '')
                )
            
            # Last resort: use content hash (ensure positive by taking absolute value)
            if not post_id:
                post_id = f"post_{abs(hash(str(post_elem)))}"
            
            # Ensure post_id is always a string and positive
            post_id = str(post_id).strip()
            if post_id.startswith('-'):
                logger.warning(f"Post ID is negative: {post_id}, taking absolute value")
                post_id = str(abs(int(post_id)))
            
            if not post_id:
                logger.warning("Could not extract post ID")
                return None
            
            # Extract title
            title = self._extract_title(post_elem)
            
            # Extract content
            content = self._extract_content(post_elem)
            
            # Check for "no posts" placeholder content
            if content and any(phrase.lower() in content.lower() for phrase in [
                "nothing here yet",
                "this user has no posts",
                "perhaps in the future",
                "private blog",
                "this blog is private"
            ]):
                logger.debug(f"Skipping placeholder post {post_id}: '{content[:100]}...'")
                return None
            
            # Skip if no meaningful content
            if not content or len(content.strip()) < 10:
                logger.debug(f"Skipping post {post_id}: insufficient content")
                return None
            
            # Extract tags
            tags = self._extract_tags(post_elem)
            
            # Extract URL
            url = self._extract_url(post_elem, base_url)
            
            # Extract creation date if available
            created_at = self._extract_date(post_elem)
            
            # Classify content type
            content_type = self._classify_content_type(content, tags)
            
            logger.debug(f"Post {post_id} classified as {content_type}: '{content[:100]}...' (tags: {tags})")
            
            return BlogPost(
                post_id=post_id,
                title=title,
                content=content,
                tags=tags,
                created_at=created_at,
                url=url,
                content_type=content_type
            )
            
        except Exception as e:
            logger.warning(f"Error extracting post data: {e}")
            return None
    
    def _extract_title(self, post_elem) -> Optional[str]:
        """Extract post title."""
        title_selectors = [
            ('h1', {'class': re.compile(r'title|post-title|entry-title')}),
            ('h2', {'class': re.compile(r'title|post-title|entry-title')}),
            ('h3', {'class': re.compile(r'title|post-title|entry-title')}),
            ('a', {'class': re.compile(r'title|post-title|entry-title')}),
            ('h1', {}),
            ('h2', {}),
            ('h3', {}),
        ]
        
        for tag, attrs in title_selectors:
            title_elem = post_elem.find(tag, attrs)
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                if title_text and len(title_text) > 3:
                    return title_text
        
        return None
    
    def _extract_content(self, post_elem) -> str:
        """Extract post content."""
        content_selectors = [
            ('div', {'class': re.compile(r'content|post-content|entry-content|text')}),
            ('p', {'class': re.compile(r'content|post-content|entry-content')}),
            ('div', {'class': re.compile(r'body|text')}),
            ('article', {}),
            ('section', {}),
        ]
        
        for tag, attrs in content_selectors:
            content_elem = post_elem.find(tag, attrs)
            if content_elem:
                # Remove script and style elements
                for script in content_elem.find_all(['script', 'style']):
                    script.decompose()
                
                content_text = content_elem.get_text(strip=True)
                if content_text and len(content_text) > 20:
                    return content_text
        
        # Fallback for sideblog posts: use .singlecommentline text blocks
        side_comments = post_elem.find_all('div', class_='singlecommentline')
        if side_comments:
            text_blocks = [c.get_text(' ', strip=True) for c in side_comments]
            joined_text = ' '.join([t for t in text_blocks if t])
            if joined_text and len(joined_text) > 20:
                return joined_text

        # Fallback: get all text from post element
        content_text = post_elem.get_text(' ', strip=True)
        return content_text
    
    def _extract_tags(self, post_elem) -> List[str]:
        """Extract post tags."""
        tags = []
        
        # Look for tag containers
        tag_containers = post_elem.find_all(
            ['div', 'span', 'ul'],
            class_=re.compile(r'tags|categories|tag')
        )
        
        for container in tag_containers:
            tag_links = container.find_all('a', class_=re.compile(r'tag'))
            for tag_link in tag_links:
                tag_text = tag_link.get_text(strip=True)
                if tag_text:
                    # Remove common prefixes
                    tag_text = re.sub(r'^#', '', tag_text)
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)
        
        return tags
    
    def _extract_url(self, post_elem, base_url: str) -> Optional[str]:
        """Extract post URL."""
        # Look for title link
        title_link = post_elem.find('a', class_=re.compile(r'title|post-title'))
        if title_link and title_link.get('href'):
            return urljoin(base_url, title_link['href'])
        
        # Look for any link within the post
        post_link = post_elem.find('a', href=re.compile(r'/post/|/blog/'))
        if post_link and post_link.get('href'):
            return urljoin(base_url, post_link['href'])
        
        return None
    
    def _extract_date(self, post_elem) -> Optional[datetime]:
        """Extract post creation date."""
        date_selectors = [
            ('time', {'class': re.compile(r'date|time|published')}),
            ('span', {'class': re.compile(r'date|time|published')}),
            ('div', {'class': re.compile(r'date|time|published')}),
            ('[datetime]', {}),
        ]
        
        for selector, attrs in date_selectors:
            if selector == '[datetime]':
                date_elem = post_elem.find(attrs={'datetime': True})
            else:
                date_elem = post_elem.find(selector, attrs)
            
            if date_elem:
                # Try datetime attribute first
                datetime_str = date_elem.get('datetime')
                if datetime_str:
                    try:
                        return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                    except:
                        pass
                
                # Try parsing text content
                date_text = date_elem.get_text(strip=True)
                if date_text:
                    # Simple date parsing - can be enhanced
                    try:
                        # Common formats
                        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y']:
                            try:
                                return datetime.strptime(date_text, fmt)
                            except:
                                continue
                    except:
                        pass
        
        return None
    
    def _classify_content_type(self, content: str, tags: List[str]) -> str:
        """
        Classify the type of post content for filtering.
        
        Args:
            content: Post content text
            tags: Post tags
        
        Returns:
            Content type: "text_clear", "image_dependent", "quiz_question", "unknown"
        """
        # Check for quiz-tagged posts first
        if any(tag.lower() == "quiz" for tag in tags):
            return "quiz_question"
        
        # Check content length and substance
        content_length = len(content.strip())
        
        # Very short content likely depends on images
        if content_length < 20:
            return "image_dependent"
        
        # Check for substantial text content with clear meaning
        # Look for complete sentences, specific expectations, or behavioral rules
        sentences = [s.strip() for s in content.split('.') if s.strip()]
        
        # Must have at least 1 complete sentence
        if len(sentences) < 1:
            return "image_dependent"
        
        # Check for attitude/behavior/relationship keywords that indicate clear expectations
        relationship_keywords = [
            'should', 'must', 'expect', 'want', 'need', 'prefer', 'like', 'dislike',
            'important', 'value', 'believe', 'think', 'feel', 'attitude', 'behavior',
            'personality', 'character', 'trait', 'quality', 'ideal', 'perfect',
            'relationship', 'partner', 'girlfriend', 'woman', 'man', 'love',
            'respect', 'trust', 'honest', 'loyal', 'kind', 'caring', 'supportive',
            'understanding', 'patient', 'compassionate', 'intelligent', 'funny',
            'ambitious', 'motivated', 'driven', 'successful', 'confident', 'independent'
        ]
        
        content_lower = content.lower()
        keyword_count = sum(1 for keyword in relationship_keywords if keyword in content_lower)
        
        # If we have enough keywords, it's likely text_clear (even if shorter)
        if keyword_count >= 2:
            return "text_clear"
        
        # Check for explicit rules or expectations
        rule_indicators = ['rule', 'expectation', 'requirement', 'standard', 'criteria', 'dealbreaker']
        if any(indicator in content_lower for indicator in rule_indicators):
            return "text_clear"
        
        # Check for phrases that indicate personal preferences/requirements
        preference_indicators = ['i want', 'i need', 'i expect', 'i prefer', 'i value', 'i appreciate']
        if any(indicator in content_lower for indicator in preference_indicators):
            return "text_clear"
        
        # Default to image_dependent if unclear
        return "image_dependent"
    
    def _dict_to_blogpost(self, post_dict: dict) -> BlogPost:
        """
        Convert dictionary to BlogPost object.
        
        Args:
            post_dict: Post dictionary
        
        Returns:
            BlogPost object
        """
        return BlogPost(
            post_id=post_dict['post_id'],
            title=post_dict.get('title'),
            content=post_dict['content'],
            tags=post_dict.get('tags', []),
            created_at=datetime.fromisoformat(post_dict['created_at']) if post_dict.get('created_at') else None,
            url=post_dict.get('url'),
            content_type=post_dict.get('content_type', 'unknown')
        )
