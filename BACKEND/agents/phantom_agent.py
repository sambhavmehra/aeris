"""
AERIS PhantomTrace Agent — Ethical, consent-based link analytics and tracking.
Creates trackable links, records visits (with analytics disclosure to visitors),
and provides rich statistics on link engagement.
"""

import re
import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from memory.phantom_store import phantom_store

logger = logging.getLogger("aeris.agent.phantom")


class PhantomAgent(BaseAgent):
    """Ethical consent-based link analytics and tracking agent."""

    def __init__(self):
        super().__init__(
            name="PhantomAgent",
            description="Ethical consent-based link analytics and tracking agent",
            task_domain="phantom",
            version="1.0.0",
            capabilities=[
                "Create Analytics Links",
                "View Link Statistics",
                "List Tracked Links",
                "Delete Tracking Links",
                "GeoIP Enrichment",
            ],
        )

    # ── Think ──────────────────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Parse intent and extract parameters from the user message."""
        lower = message.lower()

        # ── Fast keyword-based classification ──
        if any(kw in lower for kw in ("create link", "track link", "new link", "generate link", "shorten")):
            url = self._extract_url(message)
            return {"action": "create_link", "target_url": url, "message": message}

        if any(kw in lower for kw in ("stats", "statistics", "analytics", "visits", "how many")):
            link_id = self._extract_link_id(message)
            return {"action": "get_stats", "link_id": link_id, "message": message}

        if any(kw in lower for kw in ("list link", "show link", "all link", "my link", "sab link", "saare link")):
            return {"action": "list_links", "message": message}

        if any(kw in lower for kw in ("delete link", "remove link", "deactivate link", "hata", "band kar")):
            link_id = self._extract_link_id(message)
            return {"action": "delete_link", "link_id": link_id, "message": message}

        # ── Fallback: LLM-based classification ──
        classify_prompt = (
            "You are a classifier for PhantomTrace — an ethical link analytics tool.\n"
            "Classify the user's intent into exactly one of: create_link, get_stats, list_links, delete_link.\n"
            "Also extract any URL (target_url) or link ID (link_id) mentioned.\n\n"
            f"User message: {message}\n\n"
            "Respond with ONLY JSON:\n"
            '{"action": "...", "target_url": "..." or null, "link_id": "..." or null}'
        )
        try:
            raw = await ai_engine.classify(classify_prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            plan = json.loads(raw)
            plan.setdefault("message", message)
            return plan
        except Exception as e:
            logger.warning(f"Classification fallback failed: {e}")
            # Ultimate fallback — treat as list
            return {"action": "list_links", "message": message}

    # ── Execute ────────────────────────────────────────────────────

    async def execute(self, plan: Any) -> Any:
        """Run the appropriate PhantomStore operation."""
        action = plan.get("action", "list_links")

        if action == "create_link":
            target_url = plan.get("target_url")
            if not target_url:
                return {"action": "create_link", "error": "No target URL provided."}
            entry = phantom_store.create_link(target_url)
            return {"action": "create_link", "entry": entry}

        elif action == "get_stats":
            link_id = plan.get("link_id")
            if not link_id:
                return {"action": "get_stats", "error": "No link ID provided."}
            stats = phantom_store.get_stats(link_id)
            if stats is None:
                return {"action": "get_stats", "error": f"Link ID `{link_id}` not found."}
            return {"action": "get_stats", "stats": stats}

        elif action == "list_links":
            links = phantom_store.list_links()
            return {"action": "list_links", "links": links}

        elif action == "delete_link":
            link_id = plan.get("link_id")
            if not link_id:
                return {"action": "delete_link", "error": "No link ID provided."}
            success = phantom_store.delete_link(link_id)
            return {"action": "delete_link", "link_id": link_id, "success": success}

        return {"action": action, "error": f"Unknown action: {action}"}

    # ── Report ─────────────────────────────────────────────────────

    async def report(self, results: Any) -> str:
        """Format results in the Mythos/hacker aesthetic with Hinglish flair."""
        action = results.get("action")

        # ── Error handling ──
        if "error" in results:
            return (
                f"## ⚠️ PhantomTrace Error\n\n"
                f"**Error:** {results['error']}\n\n"
                f"Sir, please check the input and try again."
            )

        # ── Create Link ──
        if action == "create_link":
            entry = results["entry"]
            link_id = entry["link_id"]
            target = entry["target_url"]
            return (
                f"## 🔗 **PhantomTrace Link Created**\n\n"
                f"| Field | Value |\n"
                f"|-------|-------|\n"
                f"| **Target** | `{target}` |\n"
                f"| **Tracking Link** | `http://localhost:8000/phantom/{link_id}` |\n"
                f"| **Link ID** | `{link_id}` |\n"
                f"| **Status** | Active ✅ |\n"
                f"| **Created** | {entry['created_at']} |\n"
                f"| **Consent Notice** | Visitors will see an analytics disclosure |\n\n"
                f"Sir, yeh link fully ethical hai — har visitor ko analytics notice dikhega before redirect."
            )

        # ── Get Stats ──
        if action == "get_stats":
            stats = results["stats"]
            link_id = stats["link_id"]
            target = stats["target_url"]
            total = stats["total_visits"]
            unique = stats["unique_visitors"]
            active = "Active ✅" if stats.get("active", True) else "Inactive ❌"

            md = [
                f"## 📊 **PhantomTrace Analytics — `{link_id}`**\n",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| **Target URL** | `{target}` |",
                f"| **Status** | {active} |",
                f"| **Total Visits** | {total} |",
                f"| **Unique Visitors** | {unique} |",
                f"| **Created** | {stats['created_at']} |",
            ]

            visits = stats.get("visits", [])
            if visits:
                md.append(f"\n### 🕵️ Recent Visits (last 10)\n")
                md.append("| # | Timestamp | User-Agent | Referrer | Geo |")
                md.append("|---|-----------|------------|----------|-----|")
                for i, v in enumerate(visits[-10:], 1):
                    ua = v.get("user_agent", "—")[:50]
                    ref = v.get("referrer", "—") or "Direct"
                    geo = v.get("geo", {})
                    geo_str = f"{geo.get('city', '?')}, {geo.get('country', '?')}" if geo else "—"
                    md.append(f"| {i} | {v['timestamp']} | `{ua}` | {ref} | {geo_str} |")
            else:
                md.append("\n> No visits recorded yet.")

            md.append(f"\nSir, yeh link ke complete analytics hain — sab kuch consent-based tracked hai.")
            return "\n".join(md)

        # ── List Links ──
        if action == "list_links":
            links = results.get("links", [])
            if not links:
                return (
                    "## 👻 PhantomTrace Links\n\n"
                    "Abhi koi tracked link nahi hai, Sir. "
                    "`create link <url>` bol kar naya link banao."
                )

            md = [
                "## 👻 **PhantomTrace — All Tracked Links**\n",
                "| # | Link ID | Target URL | Visits | Status | Created |",
                "|---|---------|------------|--------|--------|---------|",
            ]
            for i, link in enumerate(links, 1):
                status = "✅ Active" if link.get("active", True) else "❌ Inactive"
                target = link["target_url"]
                if len(target) > 45:
                    target = target[:42] + "..."
                md.append(
                    f"| {i} | `{link['link_id']}` | `{target}` | "
                    f"{link['total_visits']} | {status} | {link['created_at']} |"
                )

            md.append(f"\n**Total Links:** {len(links)}")
            md.append("Sir, kisi bhi link ke stats dekhne ke liye `stats <link_id>` bolo.")
            return "\n".join(md)

        # ── Delete Link ──
        if action == "delete_link":
            link_id = results.get("link_id", "?")
            if results.get("success"):
                return (
                    f"## 🗑️ **PhantomTrace Link Deactivated**\n\n"
                    f"**Link ID:** `{link_id}`\n"
                    f"**Status:** Inactive ❌\n\n"
                    f"Sir, link `{link_id}` deactivate kar diya gaya hai. "
                    f"Data preserved hai for records, lekin ab visitors ko redirect nahi karega."
                )
            return (
                f"## ⚠️ PhantomTrace\n\n"
                f"Link ID `{link_id}` not found. `list links` se apne links check karo, Sir."
            )

        # ── Fallback ──
        return f"## 👻 PhantomTrace\n\n{json.dumps(results, indent=2)}"

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _extract_url(text: str) -> str | None:
        """Extract the first URL from the message text."""
        match = re.search(r'https?://[^\s<>"\']+', text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_link_id(text: str) -> str | None:
        """Extract an 8-char hex link ID from the message text."""
        match = re.search(r'\b([a-f0-9]{8})\b', text)
        return match.group(1) if match else None
