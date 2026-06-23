"""
AERIS Webpage Inspector Tool
═════════════════════════════
Launches a headless Chromium browser using Selenium to inspect a webpage,
capturing console logs (errors and warnings), network failures (failed responses
and resource load errors), page statistics, and saving a screenshot.
"""

import os
import json
import time
import logging
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger("AerisWebTools")

def inspect_webpage(url: str, save_screenshot: bool = True) -> str:
    """
    Inspects a website using Selenium and headless Chromium, capturing the DOM,
    console logs (errors/warnings), network logs (failed requests/responses),
    and saving a screenshot.
    
    Args:
        url: The web page URL to inspect.
        save_screenshot: Whether to save a screenshot of the page.
        
    Returns:
        A detailed Markdown report containing the page title, console messages, 
        network activity, text snippet, and screenshot info.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    start_time = time.time()
    console_logs = []
    network_requests = []
    network_errors = []
    screenshot_path = ""
    
    # Setup Chrome options with logging preferences
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('window-size=1280x720')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Enable performance and browser logs
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        
        # Navigate to target website
        driver.get(url)
        
        # Give dynamic JavaScript time to execute and resources to load
        time.sleep(3.0)
        
        # Retrieve logs safely
        browser_logs = []
        try:
            browser_logs = driver.get_log('browser')
        except Exception as le:
            logger.warning(f"Failed to retrieve browser logs: {le}")
            
        perf_logs = []
        try:
            perf_logs = driver.get_log('performance')
        except Exception as le:
            logger.warning(f"Failed to retrieve performance logs: {le}")
            
        # Parse console logs
        for entry in browser_logs:
            level = entry.get('level', 'INFO')
            message_text = entry.get('message', '')
            source = entry.get('source', '')
            console_logs.append({
                "type": level.lower(),
                "text": message_text,
                "location": source
            })
            
        # Parse performance (network) logs
        for entry in perf_logs:
            try:
                log_data = json.loads(entry['message'])['message']
                method = log_data.get('method', '')
                params = log_data.get('params', {})
                
                if method == 'Network.responseReceived':
                    response = params.get('response', {})
                    status = response.get('status', 200)
                    resp_url = response.get('url', '')
                    resp_method = params.get('type', 'GET')
                    status_text = response.get('statusText', '')
                    
                    network_requests.append({
                        "url": resp_url,
                        "status": status,
                        "method": resp_method
                    })
                    
                    if status >= 400:
                        network_errors.append({
                            "url": resp_url,
                            "status": status,
                            "status_text": status_text,
                            "method": resp_method,
                            "type": "response_error"
                        })
                        
                elif method == 'Network.loadingFailed':
                    fail_url = params.get('documentURL', '')
                    error_text = params.get('errorText', 'Unknown connection error')
                    req_id = params.get('requestId', '')
                    
                    network_errors.append({
                        "url": fail_url or f"Request ID: {req_id}",
                        "status": "FAILED",
                        "status_text": error_text,
                        "method": "LOAD",
                        "type": "load_error"
                    })
            except Exception:
                pass
                
        # DOM and content details
        title = driver.title
        final_url = driver.current_url
        
        # Get page body text safely
        try:
            body_text = driver.find_element("tag name", "body").text
        except Exception:
            body_text = ""
            
        load_time = round((time.time() - start_time) * 1000, 2)
        
        # Element counts from DOM
        scripts_count = len(driver.find_elements("tag name", "script"))
        links_count = len(driver.find_elements("tag name", "link"))
        images_count = len(driver.find_elements("tag name", "img"))
        
        # Common error keywords in body or title
        error_keywords = ["error", "failed", "exception", "refused", "timeout", "not found", "internal server error", "crash", "unhandled", "fatal", "forbidden", "unauthorized"]
        found_signatures = []
        for kw in error_keywords:
            if kw in body_text.lower() or kw in title.lower():
                found_signatures.append(kw)
                
        # Take screenshot if requested
        if save_screenshot:
            screenshots_dir = Path("d:/Sambhav Projects/AERIS/BACKEND/Screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time())
            safe_domain = url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_").replace("&", "_")[:50]
            screenshot_filename = f"inspect_{safe_domain}_{timestamp}.png"
            screenshot_path = screenshots_dir / screenshot_filename
            driver.save_screenshot(str(screenshot_path))
            
        driver.quit()
        
        # Build Markdown Report
        report = []
        report.append(f"# 🌐 Webpage Inspection Report for `{url}`\n")
        report.append("## 📊 Summary Details")
        report.append(f"- **Final URL:** `{final_url}`")
        report.append(f"- **Page Title:** `{title}`")
        report.append(f"- **Load & Render Time:** `{load_time} ms`")
        if screenshot_path:
            screenshot_uri = Path(screenshot_path).resolve().as_uri()
            report.append(f"- **Screenshot:** [View Screenshot]({screenshot_uri})")
        report.append("")
        
        # Console logs
        report.append("## 💻 Console Logs & Warnings")
        console_errors = [c for c in console_logs if c["type"] in ("error", "warning", "severe")]
        if console_errors:
            report.append(f"Found **{len(console_errors)}** errors/warnings in the browser console:")
            report.append("| Level | Message | Source |")
            report.append("|---|---|---|")
            for c in console_errors:
                text_trunc = c['text'][:120] + "..." if len(c['text']) > 120 else c['text']
                report.append(f"| `{c['type'].upper()}` | `{text_trunc}` | `{c['location']}` |")
        else:
            report.append("✅ No console errors or warnings captured.")
        report.append("")
        
        # Network failures
        report.append("## 🔌 Network Failures & Bad Statuses")
        if network_errors:
            # Deduplicate errors by URL to keep report clean
            seen_urls = set()
            unique_network_errors = []
            for ne in network_errors:
                if ne['url'] not in seen_urls:
                    seen_urls.add(ne['url'])
                    unique_network_errors.append(ne)
            
            report.append(f"Found **{len(unique_network_errors)}** unique network/resource failures:")
            report.append("| Method | URL | Status / Detail |")
            report.append("|---|---|---|")
            for ne in unique_network_errors:
                status_desc = ne.get("status")
                if ne.get("status_text"):
                    status_desc = f"{status_desc} ({ne['status_text']})"
                url_truncated = ne['url'][:80] + "..." if len(ne['url']) > 80 else ne['url']
                report.append(f"| `{ne['method']}` | [{url_truncated}]({ne['url']}) | `{status_desc}` |")
        else:
            report.append("✅ No network resource failures detected.")
        report.append("")
        
        # DOM Analysis
        report.append("## 🔍 DOM Analysis & Page Content")
        report.append(f"- **Total Script Tags:** `{scripts_count}`")
        report.append(f"- **Total Stylesheet Link Tags:** `{links_count}`")
        report.append(f"- **Total Images:** `{images_count}`")
        if found_signatures:
            sig_str = ", ".join([f"`{s}`" for s in found_signatures])
            report.append(f"- **⚠️ Error Signatures Detected in Text/Title:** {sig_str}")
        else:
            report.append("- ✅ No standard error signatures found in the page text.")
            
        report.append("\n### 📄 Page Text Snippet (First 800 chars)")
        text_snippet = body_text.strip()[:800].replace("\n", " ")
        if text_snippet:
            report.append(f"> {text_snippet}...")
        else:
            report.append("> [No text content visible in body]")
            
        return "\n".join(report)
        
    except Exception as e:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        logger.error(f"Selenium inspection error: {e}")
        return f"# ❌ Webpage Inspection Failed\n\n- **Target URL:** `{url}`\n- **Error:** {str(e)}\n\nCould not fetch or render the website. Please check if the URL is valid, if the site is down, or if there is a network/driver block."
