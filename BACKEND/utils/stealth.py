"""
AERIS Stealth & Privacy Utilities
=================================
Rotates User-Agent headers, builds realistic header fingerprints, and resolves
active HTTP/SOCKS proxies when running in hacker/privacy mode.
"""

import os
import random
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger("aeris.stealth")

# Curated list of modern browser User-Agents
USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Firefox (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Firefox (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    # Edge (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

def get_stealth_headers() -> Dict[str, str]:
    """
    Returns a realistic dictionary of HTTP headers with a rotated modern User-Agent.
    """
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",  # Do Not Track
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    
    # Randomize headers slightly to prevent static signature detection
    if "Chrome" in ua:
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"' if "Windows" in ua else '"macOS"'
        
    return headers

def get_active_proxy() -> Optional[str]:
    """
    Looks up the active proxy URL configured in environment variables.
    Checks AERIS_PROXY, socks_proxy, HTTP_PROXY, and HTTPS_PROXY in order.
    Returns None if no proxy is configured.
    """
    # Check AERIS specific proxy configuration first
    proxy = os.getenv("AERIS_PROXY")
    if proxy:
        logger.debug(f"[Stealth] Using AERIS_PROXY: {proxy}")
        return proxy.strip()
        
    # Check general standard proxy environment variables
    for var in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"]:
        val = os.getenv(var)
        if val:
            logger.debug(f"[Stealth] Using system proxy from {var}: {val}")
            return val.strip()
            
    return None

def configure_client_stealth(client_kwargs: Dict[str, Any], hacker_mode: bool = False, is_api: bool = False) -> Dict[str, Any]:
    """
    Configures client dictionary arguments for httpx with stealth headers and proxy settings.
    """
    if not hacker_mode:
        return client_kwargs

    logger.info("[Stealth] Customizing client connection with stealth profiling")
    
    # Configure proxy if available
    proxy_url = get_active_proxy()
    if proxy_url:
        client_kwargs["proxies"] = {
            "all://": proxy_url
        }
        
    if is_api:
        # Do not spoof browser headers for standard JSON API endpoints to avoid WAF/CDN flags
        return client_kwargs
    
    # Merge/replace headers with stealth ones
    current_headers = client_kwargs.get("headers", {})
    stealth_headers = get_stealth_headers()
    # Retain custom headers, but override User-Agent and key privacy markers
    stealth_headers.update(current_headers)
    client_kwargs["headers"] = stealth_headers
        
    return client_kwargs
