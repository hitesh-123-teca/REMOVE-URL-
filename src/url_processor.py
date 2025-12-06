"""
URL removal functionality
"""

import re
import logging
from typing import List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class URLProcessor:
    """Handles URL detection and removal from text"""
    
    # Comprehensive URL patterns
    URL_PATTERNS = [
        # HTTP/HTTPS URLs
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+',
        r'https?://(?:[-\w.]|(?:%[\da-f-A-F]{2}))+(?:/[-\w.%?=&]*)*',
        
        # WWW URLs without protocol
        r'www\.(?:[-\w.]|(?:%[\da-fA-F]{2}))+',
        r'www\.(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w.%?=&]*)*',
        
        # FTP URLs
        r'ftp://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w.%?=&]*)*',
        
        # Email addresses (optional)
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        
        # IP addresses
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        
        # Short URLs
        r'\b(?:bit\.ly|t\.co|goo\.gl|tinyurl|ow\.ly|is\.gd|buff\.ly|adf\.ly|shorte\.st|bc\.vc)\/[a-zA-Z0-9]+\b',
        
        # Social media handles
        r'@[a-zA-Z0-9_]+',  # Twitter/Instagram handles
        r'#\w+',  # Hashtags
    ]
    
    # Domain extensions to look for
    DOMAIN_EXTENSIONS = [
        '.com', '.org', '.net', '.edu', '.gov', '.mil',
        '.in', '.co.in', '.org.in', '.net.in', '.gen.in',
        '.us', '.uk', '.ca', '.au', '.de', '.fr', '.jp',
        '.ru', '.cn', '.br', '.it', '.es', '.mx', '.nl',
        '.se', '.no', '.dk', '.fi', '.pl', '.tr', '.ir',
        '.za', '.gr', '.th', '.vn', '.id', '.my', '.sg',
        '.ph', '.pk', '.bd', '.lk', '.np', '.bt', '.mv',
        '.info', '.biz', '.me', '.io', '.tv', '.app',
        '.dev', '.xyz', '.online', '.site', '.website',
        '.tech', '.space', '.digital', '.network', '.cloud',
        '.store', '.shop', '.blog', '.news', '.media',
        '.agency', '.company', '.services', '.solutions'
    ]
    
    def __init__(self, replacement_text: str = "[LINK REMOVED]"):
        self.replacement_text = replacement_text
        self.compiled_patterns = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile all regex patterns for efficiency"""
        for pattern in self.URL_PATTERNS:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                self.compiled_patterns.append(compiled)
            except re.error as e:
                logger.warning(f"Invalid regex pattern: {pattern} - {e}")
    
    def find_urls(self, text: str) -> List[Tuple[str, str]]:
        """
        Find all URLs in text
        Returns list of tuples (url, url_type)
        """
        if not text:
            return []
        
        found_urls = []
        
        # Check with compiled patterns
        for pattern in self.compiled_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                url = match.group()
                url_type = self._classify_url(url)
                found_urls.append((url, url_type))
        
        # Also check for domain-like patterns
        words = text.split()
        for word in words:
            # Check if word looks like a domain
            if self._looks_like_domain(word):
                found_urls.append((word, "DOMAIN"))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url, url_type in found_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append((url, url_type))
        
        return unique_urls
    
    def _classify_url(self, url: str) -> str:
        """Classify the type of URL"""
        url_lower = url.lower()
        
        if url_lower.startswith('http://'):
            return "HTTP"
        elif url_lower.startswith('https://'):
            return "HTTPS"
        elif url_lower.startswith('ftp://'):
            return "FTP"
        elif url_lower.startswith('www.'):
            return "WWW"
        elif '@' in url_lower and '.' in url_lower:
            return "EMAIL"
        elif url_lower.startswith('@'):
            return "MENTION"
        elif url_lower.startswith('#'):
            return "HASHTAG"
        elif any(shortener in url_lower for shortener in ['bit.ly', 't.co', 'goo.gl']):
            return "SHORTENER"
        elif re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', url_lower):
            return "IP_ADDRESS"
        else:
            return "UNKNOWN"
    
    def _looks_like_domain(self, text: str) -> bool:
        """Check if text looks like a domain"""
        # Remove punctuation at the end
        text = text.strip('.,;:!?')
        
        # Check for domain extensions
        for ext in self.DOMAIN_EXTENSIONS:
            if text.lower().endswith(ext):
                # Ensure it has something before the extension
                if len(text) > len(ext):
                    return True
        
        return False
    
    def remove_urls(self, text: str, replacement: Optional[str] = None) -> str:
        """
        Remove all URLs from text and replace with custom text
        """
        if not text:
            return text
        
        if replacement is None:
            replacement = self.replacement_text
        
        # Find all URLs first
        urls = self.find_urls(text)
        
        if not urls:
            return text
        
        # Replace each URL
        cleaned_text = text
        for url, url_type in urls:
            # Special handling for different URL types
            if url_type == "EMAIL":
                replacement_text = "[EMAIL REMOVED]"
            elif url_type == "MENTION":
                replacement_text = ""  # Remove mentions completely
            elif url_type == "HASHTAG":
                replacement_text = url  # Keep hashtags
            else:
                replacement_text = replacement
            
            # Escape special regex characters in URL
            url_escaped = re.escape(url)
            cleaned_text = re.sub(url_escaped, replacement_text, cleaned_text)
        
        # Additional cleanup
        cleaned_text = self._cleanup_text(cleaned_text)
        
        return cleaned_text.strip()
    
    def _cleanup_text(self, text: str) -> str:
        """Additional text cleanup"""
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Remove empty parentheses/brackets
        text = re.sub(r'\[\s*\]', '', text)
        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'\{\s*\}', '', text)
        
        # Fix punctuation spacing
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        text = re.sub(r'([.,;:!?])(\w)', r'\1 \2', text)
        
        return text
    
    def extract_urls_only(self, text: str) -> List[str]:
        """Extract only URLs from text"""
        urls = self.find_urls(text)
        return [url for url, _ in urls]
    
    def count_urls(self, text: str) -> Dict[str, int]:
        """Count URLs by type"""
        urls = self.find_urls(text)
        
        counts = {}
        for _, url_type in urls:
            counts[url_type] = counts.get(url_type, 0) + 1
        
        return counts
    
    def is_safe_url(self, url: str) -> bool:
        """
        Check if URL appears to be safe
        Note: This is a basic check, not a substitute for proper security
        """
        try:
            parsed = urlparse(url)
            
            # Check for suspicious patterns
            suspicious_patterns = [
                r'\.exe$', r'\.bat$', r'\.cmd$', r'\.scr$',
                r'\.zip$', r'\.rar$', r'\.7z$',
                r'login', r'password', r'admin', r'secure',
                r'bank', r'paypal', r'credit', r'card'
            ]
            
            url_lower = url.lower()
            for pattern in suspicious_patterns:
                if re.search(pattern, url_lower):
                    return False
            
            # Check for IP addresses (can be suspicious)
            if re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', parsed.netloc):
                return False
            
            return True
            
        except Exception:
            return False
