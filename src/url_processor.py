"""
URL removal functionality
"""

import re
import logging
from typing import List, Optional, Tuple, Dict   # ✅ Dict added
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class URLProcessor:
    """Handles URL detection and removal from text"""
    
    # Comprehensive URL patterns
    URL_PATTERNS = [
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+',
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w.%?=&]*)*',
        r'www\.(?:[-\w.]|(?:%[\da-fA-F]{2}))+',
        r'www\.(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w.%?=&]*)*',
        r'ftp://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w.%?=&]*)*',
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        r'\b(?:bit\.ly|t\.co|goo\.gl|tinyurl|ow\.ly|is\.gd|buff\.ly|adf\.ly|shorte\.st|bc\.vc)\/[a-zA-Z0-9]+\b',
        r'@[a-zA-Z0-9_]+',
        r'#\w+',
    ]
    
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
        for pattern in self.URL_PATTERNS:
            try:
                self.compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid regex pattern: {pattern} - {e}")
    
    def find_urls(self, text: str) -> List[Tuple[str, str]]:
        if not text:
            return []
        
        found_urls = []
        
        for pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                url = match.group()
                url_type = self._classify_url(url)
                found_urls.append((url, url_type))
        
        words = text.split()
        for word in words:
            if self._looks_like_domain(word):
                found_urls.append((word, "DOMAIN"))
        
        seen = set()
        unique_urls = []
        for url, url_type in found_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append((url, url_type))
        
        return unique_urls
    
    def _classify_url(self, url: str) -> str:
        url_lower = url.lower()
        
        if url_lower.startswith('http://'):
            return "HTTP"
        if url_lower.startswith('https://'):
            return "HTTPS"
        if url_lower.startswith('ftp://'):
            return "FTP"
        if url_lower.startswith('www.'):
            return "WWW"
        if '@' in url_lower and '.' in url_lower:
            return "EMAIL"
        if url_lower.startswith('@'):
            return "MENTION"
        if url_lower.startswith('#'):
            return "HASHTAG"
        if any(shortener in url_lower for shortener in ['bit.ly', 't.co', 'goo.gl']):
            return "SHORTENER"
        if re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', url_lower):
            return "IP_ADDRESS"
        return "UNKNOWN"
    
    def _looks_like_domain(self, text: str) -> bool:
        text = text.strip('.,;:!?')
        return any(text.lower().endswith(ext) and len(text) > len(ext) for ext in self.DOMAIN_EXTENSIONS)
    
    def remove_urls(self, text: str, replacement: Optional[str] = None) -> str:
        if not text:
            return text
        
        if replacement is None:
            replacement = self.replacement_text
        
        urls = self.find_urls(text)
        if not urls:
            return text
        
        cleaned_text = text
        for url, url_type in urls:
            if url_type == "EMAIL":
                rep = "[EMAIL REMOVED]"
            elif url_type == "MENTION":
                rep = ""
            elif url_type == "HASHTAG":
                rep = url
            else:
                rep = replacement
            
            cleaned_text = re.sub(re.escape(url), rep, cleaned_text)
        
        return self._cleanup_text(cleaned_text).strip()
    
    def _cleanup_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\[\s*\]|\(\s*\)|\{\s*\}', '', text)
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        text = re.sub(r'([.,;:!?])(\w)', r'\1 \2', text)
        return text
    
    def extract_urls_only(self, text: str) -> List[str]:
        return [url for url, _ in self.find_urls(text)]
    
    def count_urls(self, text: str) -> Dict[str, int]:   # ⚠️ now Dict works
        urls = self.find_urls(text)
        counts = {}
        for _, url_type in urls:
            counts[url_type] = counts.get(url_type, 0) + 1
        return counts
    
    def is_safe_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            suspicious_patterns = [
                r'\.exe$', r'\.bat$', r'\.cmd$', r'\.scr$',
                r'\.zip$', r'\.rar$', r'\.7z$',
                r'login', r'password', r'admin', r'secure',
                r'bank', r'paypal', r'credit', r'card'
            ]
            
            url_lower = url.lower()
            if any(re.search(pattern, url_lower) for pattern in suspicious_patterns):
                return False
            
            if re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', parsed.netloc):
                return False
            
            return True
        except Exception:
            return False
