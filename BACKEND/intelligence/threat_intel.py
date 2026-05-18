"""
AERIS Threat Intelligence Agent
Ported from VulnSage's threat_intel_agent.py.

Fetches live CVE data from:
- NVD (National Vulnerability Database) API v2
- CISA Known Exploited Vulnerabilities (KEV) catalog

Results are cached to disk with a 24-hour TTL.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("aeris.intelligence.threat_intel")

# Cache location relative to this file's parent (BACKEND/)
_DEFAULT_CACHE = str(Path(__file__).resolve().parent.parent / "data" / "threat_intel_cache.json")
CACHE_TTL_HOURS = 24


class ThreatIntelAgent:
    """Fetch and normalize recent vulnerability intelligence from public feeds."""

    NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    def __init__(self, cache_path: str = _DEFAULT_CACHE, timeout: int = 20):
        self.cache_path = cache_path
        self.timeout = timeout
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────

    def collect_latest(self, max_items: int = 120, days: int = 30, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Return the latest threat intelligence.
        Uses the on-disk cache unless it's stale or force_refresh is True.
        """
        if not force_refresh and self._cache_is_fresh():
            logger.info("Returning cached threat intel (cache is fresh)")
            return self.load_cached()

        logger.info("Fetching fresh threat intel from NVD + CISA KEV...")
        nvd_items = self._fetch_nvd(max_items=max_items, days=days)
        kev_items = self._fetch_cisa_kev(max_items=max_items)

        merged: Dict[str, Dict] = {}
        for item in nvd_items + kev_items:
            key = item.get("id") or f"{item.get('source')}::{item.get('title', '')[:60]}"
            if key not in merged:
                merged[key] = item

        items = sorted(merged.values(), key=lambda x: x.get("published", ""), reverse=True)[:max_items]

        payload: Dict[str, Any] = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "total_items": len(items),
            "sources": {"nvd": len(nvd_items), "cisa_kev": len(kev_items)},
            "items": items,
        }
        self._save_cache(payload)
        logger.info("Threat intel collected: %d items (NVD=%d, CISA=%d)", len(items), len(nvd_items), len(kev_items))
        return payload

    def load_cached(self) -> Dict[str, Any]:
        """Load cached threat intel from disk. Returns empty structure if not found."""
        if not os.path.exists(self.cache_path):
            return {"collected_at": None, "total_items": 0, "sources": {}, "items": []}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Cache load failed: %s", exc)
            return {"collected_at": None, "total_items": 0, "sources": {}, "items": []}

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search cached threat intel for matching CVEs/keywords."""
        data = self.load_cached()
        query_lower = query.lower()
        results = []
        for item in data.get("items", []):
            searchable = f"{item.get('id','')} {item.get('title','')} {item.get('description','')}".lower()
            if query_lower in searchable:
                results.append(item)
            if len(results) >= limit:
                break
        return results

    def get_critical_cves(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return Critical-severity CVEs from cache."""
        data = self.load_cached()
        critical = [i for i in data.get("items", []) if i.get("severity", "").upper() in ("CRITICAL", "HIGH")]
        return critical[:limit]

    def get_known_exploited(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return CISA KEV entries (actively exploited in the wild)."""
        data = self.load_cached()
        return [i for i in data.get("items", []) if i.get("known_exploited")][:limit]

    def get_summary(self) -> Dict[str, Any]:
        """Return a quick summary of cached intel."""
        data = self.load_cached()
        items = data.get("items", [])
        sev_counts: Dict[str, int] = {}
        for item in items:
            sev = item.get("severity", "Unknown")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        return {
            "collected_at": data.get("collected_at"),
            "total_items": data.get("total_items", 0),
            "sources": data.get("sources", {}),
            "severity_breakdown": sev_counts,
            "known_exploited": sum(1 for i in items if i.get("known_exploited")),
            "cache_fresh": self._cache_is_fresh(),
        }

    # ── NVD fetcher ──────────────────────────────────────────────────

    def _fetch_nvd(self, max_items: int, days: int) -> List[Dict[str, Any]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        results_per_page = min(200, max_items)
        start_index = 0
        all_items: List[Dict[str, Any]] = []

        while len(all_items) < max_items:
            params = {
                "pubStartDate": start.isoformat().replace("+00:00", "Z"),
                "pubEndDate": end.isoformat().replace("+00:00", "Z"),
                "resultsPerPage": results_per_page,
                "startIndex": start_index,
            }
            try:
                res = requests.get(self.NVD_API_URL, params=params, timeout=self.timeout)
                res.raise_for_status()
                data = res.json()
            except Exception as exc:
                logger.warning("NVD fetch failed: %s", exc)
                break

            vulns = data.get("vulnerabilities", [])
            if not vulns:
                break

            for entry in vulns:
                cve = entry.get("cve", {})
                cve_id = cve.get("id", "N/A")
                descriptions = cve.get("descriptions", [])
                desc = self._pick_english(descriptions)
                metrics = cve.get("metrics", {})
                severity = self._extract_severity(metrics)
                score = self._extract_score(metrics)
                cwe = self._extract_cwe(cve.get("weaknesses", []))

                all_items.append({
                    "id": cve_id,
                    "source": "NVD",
                    "title": cve_id,
                    "description": desc,
                    "severity": severity,
                    "cvss_score": score,
                    "cwe_id": cwe,
                    "published": cve.get("published", ""),
                    "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    "known_exploited": False,
                })
                if len(all_items) >= max_items:
                    break

            if len(vulns) < results_per_page:
                break
            start_index += results_per_page

        return all_items

    # ── CISA KEV fetcher ─────────────────────────────────────────────

    def _fetch_cisa_kev(self, max_items: int) -> List[Dict[str, Any]]:
        try:
            res = requests.get(self.CISA_KEV_URL, timeout=self.timeout)
            res.raise_for_status()
            data = res.json()
        except Exception as exc:
            logger.warning("CISA KEV fetch failed: %s", exc)
            return []

        items = []
        for v in data.get("vulnerabilities", [])[:max_items]:
            cve_id = v.get("cveID", "N/A")
            items.append({
                "id": cve_id,
                "source": "CISA_KEV",
                "title": v.get("vulnerabilityName", cve_id),
                "description": f"{v.get('shortDescription', '')} Vendor: {v.get('vendorProject', '')}. Product: {v.get('product', '')}.",
                "severity": "High",
                "cvss_score": None,
                "cwe_id": None,
                "published": v.get("dateAdded", ""),
                "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                "known_exploited": True,
                "kev_due_date": v.get("dueDate", ""),
                "known_ransomware_campaign_use": v.get("knownRansomwareCampaignUse", ""),
            })
        return items

    # ── Helpers ──────────────────────────────────────────────────────

    def _cache_is_fresh(self) -> bool:
        if not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            collected_at = data.get("collected_at")
            if not collected_at:
                return False
            collected = datetime.fromisoformat(collected_at)
            if collected.tzinfo is None:
                collected = collected.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - collected) < timedelta(hours=CACHE_TTL_HOURS)
        except Exception:
            return False

    def _save_cache(self, payload: Dict[str, Any]) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            logger.warning("Cache save failed: %s", exc)

    def _pick_english(self, items: List[Dict]) -> str:
        for item in items:
            if item.get("lang") == "en":
                return item.get("value", "")
        return items[0].get("value", "") if items else ""

    def _extract_severity(self, metrics: Dict) -> str:
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            records = metrics.get(key, [])
            if records:
                sev = records[0].get("cvssData", {}).get("baseSeverity")
                if sev:
                    return str(sev).title()
        return "Medium"

    def _extract_score(self, metrics: Dict) -> Optional[float]:
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            records = metrics.get(key, [])
            if records:
                score = records[0].get("cvssData", {}).get("baseScore")
                if score is not None:
                    return score
        return None

    def _extract_cwe(self, weaknesses: List[Dict]) -> Optional[str]:
        for w in weaknesses:
            for d in w.get("description", []):
                val = d.get("value", "")
                if val.startswith("CWE-"):
                    return val
        return None


_instance: Optional[ThreatIntelAgent] = None


def get_threat_intel_agent() -> ThreatIntelAgent:
    global _instance
    if _instance is None:
        _instance = ThreatIntelAgent()
    return _instance
