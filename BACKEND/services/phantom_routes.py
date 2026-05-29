"""
PhantomTrace Routes — Ethical consent-based link analytics endpoints.
Mounted in the main AERIS API server.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger("aeris.phantom")

router = APIRouter()


class PhantomCreateRequest(BaseModel):
    target_url: str
    label: str = ""


@router.post("/api/phantom/create")
async def create_phantom_link(req: PhantomCreateRequest):
    from memory.phantom_store import phantom_store
    if not req.target_url.strip():
        return {"success": False, "error": "target_url is required"}
    entry = phantom_store.create_link(req.target_url.strip())
    return {
        "success": True,
        "link_id": entry["link_id"],
        "tracking_url": f"http://localhost:8000/phantom/{entry['link_id']}",
        "target_url": entry["target_url"],
        "created_at": entry["created_at"]
    }


@router.get("/api/phantom/links")
async def list_phantom_links():
    from memory.phantom_store import phantom_store
    return {"success": True, "links": phantom_store.list_links()}


@router.get("/api/phantom/stats/{link_id}")
async def get_phantom_stats(link_id: str):
    from memory.phantom_store import phantom_store
    stats = phantom_store.get_stats(link_id)
    if stats is None:
        return {"success": False, "error": f"Link '{link_id}' not found"}
    return {"success": True, **stats}


@router.delete("/api/phantom/{link_id}")
async def delete_phantom_link(link_id: str):
    from memory.phantom_store import phantom_store
    deleted = phantom_store.delete_link(link_id)
    return {"success": deleted, "link_id": link_id}


@router.get("/phantom/{link_id}")
async def phantom_redirect(link_id: str, request: Request):
    """
    Consent-based redirect endpoint.
    Shows a clear analytics disclosure notice, logs the visit, then redirects.
    """
    from memory.phantom_store import phantom_store
    
    target_url = phantom_store.get_target_url(link_id)
    if not target_url:
        return HTMLResponse(
            content="<html><body style='background:#0a0a0a;color:#ff3333;font-family:monospace;display:flex;justify-content:center;align-items:center;height:100vh;'><h1>⚠️ PhantomTrace: Link not found or expired.</h1></body></html>",
            status_code=404
        )
    
    # Log the visit with hashed IP
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    referrer = request.headers.get("referer", "")
    
    # Basic GeoIP placeholder (can be enhanced later)
    geo = {"ip_region": "unknown"}
    
    phantom_store.log_visit(
        link_id=link_id,
        ip=client_ip,
        user_agent=user_agent,
        referrer=referrer,
        geo=geo
    )
    logger.info(f"[PhantomTrace] Visit logged for link {link_id} -> {target_url}")
    
    # Show consent notice page with auto-redirect
    consent_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AERIS PhantomTrace — Analytics Notice</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background: #0a0a0a;
                color: #00ffaa;
                font-family: 'JetBrains Mono', monospace;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                overflow: hidden;
            }}
            .container {{
                text-align: center;
                max-width: 500px;
                padding: 40px;
                border: 1px solid rgba(0, 255, 170, 0.3);
                border-radius: 12px;
                background: rgba(0, 255, 170, 0.03);
                box-shadow: 0 0 40px rgba(0, 255, 170, 0.08);
            }}
            .logo {{ font-size: 28px; font-weight: 600; color: #00ffff; margin-bottom: 16px; letter-spacing: 4px; }}
            .notice {{ font-size: 12px; color: rgba(0, 255, 170, 0.7); line-height: 1.8; margin-bottom: 20px; }}
            .notice strong {{ color: #00ffaa; }}
            .redirect-text {{ font-size: 11px; color: rgba(0, 255, 255, 0.5); letter-spacing: 2px; }}
            .progress-bar {{
                width: 100%;
                height: 3px;
                background: rgba(0, 255, 170, 0.1);
                border-radius: 2px;
                margin-top: 16px;
                overflow: hidden;
            }}
            .progress-fill {{
                height: 100%;
                width: 0%;
                background: linear-gradient(90deg, #00ffff, #00ffaa);
                border-radius: 2px;
                animation: fill 3s linear forwards;
            }}
            @keyframes fill {{
                to {{ width: 100%; }}
            }}
            .shield {{ font-size: 36px; margin-bottom: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="shield">🛡️</div>
            <div class="logo">PHANTOMTRACE</div>
            <div class="notice">
                <strong>Analytics Notice:</strong> This link is monitored by AERIS for analytics purposes.<br>
                Your visit metadata (timestamp, browser type) is being recorded.<br>
                <strong>IP addresses are hashed</strong> — no raw IPs are stored.<br>
                No cookies or browser fingerprinting is used.
            </div>
            <div class="redirect-text">REDIRECTING IN 3 SECONDS...</div>
            <div class="progress-bar"><div class="progress-fill"></div></div>
        </div>
        <script>
            setTimeout(function() {{
                window.location.href = "{target_url}";
            }}, 3000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=consent_html, status_code=200)
