"""
AERIS Zero-Day Hunter
Ported from VulnSage's zeroday_hunter.py.
Advanced active probing: HTTP smuggling, SSTI, prototype pollution,
cache poisoning, and JWT analysis.
"""
from __future__ import annotations

import base64, hashlib, hmac, json, logging, math, random, re
import socket, string, time, urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("aeris.intelligence.zeroday_hunter")

DEFAULT_TIMEOUT = 12
ENTROPY_THRESHOLD = 4.2
JWT_COMMON_SECRETS = [
    "secret", "password", "123456", "admin", "jwt_secret", "change_me",
    "supersecret", "letmein", "qwerty", "default", "test", "dev",
]


@dataclass
class ZeroDayFinding:
    id: str
    scan_id: str
    target: str
    vuln_type: str
    severity: str
    cvss_score: float
    title: str
    description: str
    reproduction: str
    remediation: str
    cve_refs: List[str]
    evidence: Dict[str, Any]
    tags: List[str]
    discovered_at: str
    llm_analysis: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "scan_id": self.scan_id, "target": self.target,
            "vuln_type": self.vuln_type, "severity": self.severity,
            "cvss_score": self.cvss_score, "title": self.title,
            "description": self.description, "reproduction": self.reproduction,
            "remediation": self.remediation, "cve_refs": self.cve_refs,
            "evidence": self.evidence, "tags": self.tags,
            "discovered_at": self.discovered_at, "llm_analysis": self.llm_analysis,
        }


def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "AERIS-ZeroDayHunter/1.0 (Security Research)", "Accept": "*/*"})
    return s

def _gen_id() -> str:
    return f"ZD-{int(time.time())}-{''.join(random.choices(string.ascii_lowercase+string.digits,k=8))}"

def _truncate(text: str, limit: int = 512) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")

def _shannon(data: str) -> float:
    if not data: return 0.0
    freq = {}
    for c in data: freq[c] = freq.get(c, 0) + 1
    t = len(data)
    return -sum((v/t)*math.log2(v/t) for v in freq.values())

def _safe_get(session, url, **kw):
    try: return session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True, **kw)
    except: return None

def _safe_post(session, url, **kw):
    try: return session.post(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True, **kw)
    except: return None

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════
#  MODULE 1 — HTTP Request Smuggling
# ═══════════════════════════════════════════════════════════

class HTTPSmugglingDetector:
    CL_TE_PROBE = (
        "POST {path} HTTP/1.1\r\nHost: {host}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Content-Length: 6\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nG"
    )
    TE_VARIANTS = [
        "Transfer-Encoding: xchunked", "Transfer-Encoding : chunked",
        "Transfer-Encoding: chunked, identity", "Transfer-Encoding: Chunked",
    ]

    def __init__(self, target: str, scan_id: str):
        self.target = target
        self.scan_id = scan_id
        p = urllib.parse.urlparse(target)
        self.host = p.netloc
        self.path = p.path or "/"
        self.port = p.port or (443 if p.scheme == "https" else 80)
        self.use_tls = p.scheme == "https"

    def _raw(self, raw: str, timeout: float = 10.0) -> Tuple[int, str, float]:
        import ssl
        t0 = time.perf_counter()
        try:
            sock = socket.create_connection((self.host.split(":")[0], self.port), timeout=timeout)
            if self.use_tls:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                sock = ctx.wrap_socket(sock, server_hostname=self.host.split(":")[0])
            sock.sendall(raw.encode("utf-8", errors="replace"))
            resp = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk or len(resp) > 8192: break
                resp += chunk
            sock.close()
            delta = (time.perf_counter() - t0) * 1000
            text = resp.decode("utf-8", errors="replace")
            status = int(text.split(" ")[1]) if " " in text[:20] else 0
            return status, _truncate(text), delta
        except socket.timeout:
            return -1, "TIMEOUT", (time.perf_counter() - t0) * 1000
        except Exception as exc:
            return -2, str(exc), 0.0

    def detect(self) -> List[ZeroDayFinding]:
        findings = []
        raw = self.CL_TE_PROBE.format(host=self.host, path=self.path)
        s1, b1, d1 = self._raw(raw)
        _, _, d2 = self._raw(raw)
        if s1 == 400 or (d1 > 9000 and d2 < 2000):
            findings.append(ZeroDayFinding(
                id=_gen_id(), scan_id=self.scan_id, target=self.target,
                vuln_type="HTTP_REQUEST_SMUGGLING_CL_TE", severity="CRITICAL", cvss_score=9.0,
                title="HTTP Request Smuggling (CL.TE)",
                description="Server processes Content-Length before Transfer-Encoding, enabling request desync attacks.",
                reproduction="1. Send CL.TE desync probe.\n2. Follow with a normal GET request.\n3. Observe unexpected prefix in response.",
                remediation="Ensure front-end and back-end agree on framing header. Prefer HTTP/2 end-to-end.",
                cve_refs=["CVE-2019-9511", "CVE-2020-11724"],
                evidence={"request": _truncate(raw), "status": s1, "delta_ms": d1},
                tags=["http-smuggling", "desync", "critical"],
                discovered_at=_now(),
            ))
        return findings


# ═══════════════════════════════════════════════════════════
#  MODULE 2 — Server-Side Template Injection (SSTI)
# ═══════════════════════════════════════════════════════════

class SSTIDetector:
    PROBES: List[Tuple[str, str, str]] = [
        ("{{7*7}}", "49", "Jinja2/Twig"),
        ("${7*7}", "49", "Freemarker/EL"),
        ("#{7*7}", "49", "Velocity/OGNL"),
        ("{{7*'7'}}", "7777777", "Jinja2"),
        ("*{7*7}", "49", "Spring SpEL"),
        ("{{config}}", "Config", "Jinja2-Flask"),
        ("#set($x=42)$x", "42", "Velocity"),
    ]

    def __init__(self, target: str, scan_id: str, session: requests.Session):
        self.target = target
        self.scan_id = scan_id
        self.session = session

    def _inject(self, url: str, param: str, payload: str) -> Tuple[Optional[requests.Response], float]:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        qs[param] = [payload]
        new_url = parsed._replace(query=urllib.parse.urlencode(qs, doseq=True)).geturl()
        t0 = time.perf_counter()
        resp = _safe_get(self.session, new_url)
        return resp, (time.perf_counter() - t0) * 1000

    def detect(self, urls: List[str]) -> List[ZeroDayFinding]:
        findings: List[ZeroDayFinding] = []
        seen: Set[str] = set()
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            params = list(urllib.parse.parse_qs(parsed.query).keys()) or ["q", "search", "id", "input", "name"]
            for param in params:
                for payload, pattern, engine in self.PROBES:
                    resp, delta = self._inject(url, param, payload)
                    if resp is None: continue
                    if re.search(pattern, resp.text or ""):
                        key = f"{url}:{param}:{engine}"
                        if key in seen: continue
                        seen.add(key)
                        findings.append(ZeroDayFinding(
                            id=_gen_id(), scan_id=self.scan_id, target=self.target,
                            vuln_type="SSTI", severity="CRITICAL", cvss_score=9.8,
                            title=f"Server-Side Template Injection ({engine}) in `{param}`",
                            description=f"Parameter `{param}` is injected into a {engine} template without sanitisation. Payload `{payload}` evaluated to `{pattern}`, confirming code execution context.",
                            reproduction=f"GET {url} with `{param}={urllib.parse.quote(payload)}` — observe `{pattern}` in response.",
                            remediation="Never pass user input into template render calls. Use sandbox environments or logic-less templates.",
                            cve_refs=["CVE-2016-4977", "CVE-2019-11043"],
                            evidence={"url": resp.url, "status": resp.status_code, "delta_ms": delta, "payload": payload},
                            tags=["ssti", "rce", engine.lower()],
                            discovered_at=_now(),
                        ))
        return findings


# ═══════════════════════════════════════════════════════════
#  MODULE 3 — Prototype Pollution
# ═══════════════════════════════════════════════════════════

class PrototypePollutionDetector:
    MARKER = "aeris_pp_marker"
    SERVER_PAYLOADS = [
        f'{{"__proto__":{{"polluted":"{MARKER}"}}}}',
        f'{{"constructor":{{"prototype":{{"polluted":"{MARKER}"}}}}}}',
        f'{{"__proto__":{{"status":555}}}}',
    ]
    QS_PAYLOADS = [
        f"__proto__[polluted]={MARKER}",
        f"constructor[prototype][polluted]={MARKER}",
    ]

    def __init__(self, target: str, scan_id: str, session: requests.Session):
        self.target, self.scan_id, self.session = target, scan_id, session

    def detect(self, endpoints: List[str]) -> List[ZeroDayFinding]:
        findings: List[ZeroDayFinding] = []
        seen: Set[str] = set()
        for url in endpoints:
            for payload in self.SERVER_PAYLOADS:
                try:
                    resp = self.session.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=DEFAULT_TIMEOUT)
                except: continue
                body = resp.text or ""
                key_base = f"pp:{url}"
                if resp.status_code == 555 and f"{key_base}:status" not in seen:
                    seen.add(f"{key_base}:status")
                    findings.append(self._make(url, payload, resp, body, 88.0,
                        "Server-Side Prototype Pollution (HTTP 555 status override)",
                        "Server returned HTTP 555 after `__proto__.status=555` injection — prototype chain is polluted.", 9.0, "CRITICAL"))
                elif self.MARKER in body and f"{key_base}:reflect" not in seen:
                    seen.add(f"{key_base}:reflect")
                    findings.append(self._make(url, payload, resp, body, 82.0,
                        "Server-Side Prototype Pollution (marker reflection)",
                        f"Injected marker `{self.MARKER}` was reflected in the response — serialised output not sanitised.", 8.5, "HIGH"))
            for qs in self.QS_PAYLOADS:
                sep = "&" if "?" in url else "?"
                resp = _safe_get(self.session, f"{url}{sep}{qs}")
                if resp and self.MARKER in (resp.text or "") and f"pp:qs:{url}" not in seen:
                    seen.add(f"pp:qs:{url}")
                    findings.append(self._make(url, qs, resp, resp.text, 75.0,
                        "Prototype Pollution via Query String",
                        f"Query-string payload `{qs}` caused marker reflection.", 7.5, "HIGH"))
        return findings

    def _make(self, url, payload, resp, body, conf, title, desc, cvss, sev) -> ZeroDayFinding:
        return ZeroDayFinding(
            id=_gen_id(), scan_id=self.scan_id, target=self.target,
            vuln_type="PROTOTYPE_POLLUTION", severity=sev, cvss_score=cvss,
            title=title, description=desc,
            reproduction=f"POST {url}\nContent-Type: application/json\n\n{payload}\nObserve response.",
            remediation="Use `Object.freeze(Object.prototype)`. Upgrade qs >= 6.7.3, body-parser >= 1.19.1, lodash >= 4.17.21.",
            cve_refs=["CVE-2019-10744", "CVE-2019-11358"],
            evidence={"url": url, "status": resp.status_code, "confidence": conf, "snippet": _truncate(body, 256)},
            tags=["prototype-pollution", "nodejs"],
            discovered_at=_now(),
        )


# ═══════════════════════════════════════════════════════════
#  MODULE 4 — Cache Poisoning
# ═══════════════════════════════════════════════════════════

class CachePoisoningDetector:
    MARKER = f"aeris-cache-{random.randint(100000,999999)}"
    UNKEYED_HEADERS = [
        ("X-Forwarded-Host", ""), ("X-Host", ""), ("X-Forwarded-Server", ""),
    ]

    def __init__(self, target: str, scan_id: str, session: requests.Session):
        self.target, self.scan_id, self.session = target, scan_id, session
        marker = self.MARKER
        self.UNKEYED_HEADERS = [
            ("X-Forwarded-Host", marker), ("X-Host", marker),
            ("X-Forwarded-Server", marker), ("X-Original-URL", f"/{marker}"),
        ]

    def detect(self) -> List[ZeroDayFinding]:
        findings: List[ZeroDayFinding] = []
        baseline = _safe_get(self.session, self.target)
        if not baseline: return findings
        for hdr, val in self.UNKEYED_HEADERS:
            resp = _safe_get(self.session, self.target, headers={hdr: val})
            if resp is None: continue
            body = resp.text or ""
            if self.MARKER in body or val.lstrip("/") in body:
                confirm = _safe_get(self.session, self.target)
                cached = confirm and (self.MARKER in (confirm.text or ""))
                findings.append(ZeroDayFinding(
                    id=_gen_id(), scan_id=self.scan_id, target=self.target,
                    vuln_type="CACHE_POISONING",
                    severity="CRITICAL" if cached else "HIGH",
                    cvss_score=9.3 if cached else 7.5,
                    title=f"Web Cache Poisoning via `{hdr}`",
                    description=(f"Server reflects unkeyed header `{hdr}` into response. "
                                 + ("Poisoned response was cached and confirmed." if cached else "Caching not confirmed.")),
                    reproduction=f"1. GET {self.target} with `{hdr}: {val}`\n2. Observe marker in response.\n3. Confirm with plain GET.",
                    remediation=f"Remove `{hdr}` from forwarded headers. Add to cache key or strip at CDN layer.",
                    cve_refs=["CVE-2018-6389"],
                    evidence={"header": hdr, "value": val, "cached": cached, "status": resp.status_code},
                    tags=["cache-poisoning", hdr.lower()],
                    discovered_at=_now(),
                ))
                break
        return findings


# ═══════════════════════════════════════════════════════════
#  MODULE 5 — JWT Analyzer
# ═══════════════════════════════════════════════════════════

class JWTAnalyzer:
    JWT_RE = re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*')

    def __init__(self, target: str, scan_id: str, session: requests.Session):
        self.target, self.scan_id, self.session = target, scan_id, session

    def _extract_jwts(self, resp: requests.Response) -> List[str]:
        tokens = self.JWT_RE.findall(resp.text or "")
        for v in resp.cookies.values(): tokens += self.JWT_RE.findall(v)
        for v in resp.headers.values(): tokens += self.JWT_RE.findall(v)
        return list(set(tokens))

    def _decode_part(self, part: str) -> Dict:
        padded = part + "=" * (-len(part) % 4)
        try: return json.loads(base64.urlsafe_b64decode(padded))
        except: return {}

    def _forge_none(self, header: Dict, payload: Dict) -> str:
        h = header.copy(); h["alg"] = "none"
        def b64(d): return base64.urlsafe_b64encode(json.dumps(d, separators=(",",":")).encode()).rstrip(b"=").decode()
        return f"{b64(h)}.{b64(payload)}."

    def _forge_hs256(self, header: Dict, payload: Dict, secret: str) -> str:
        def b64(d): return base64.urlsafe_b64encode(json.dumps(d, separators=(",",":")).encode()).rstrip(b"=").decode()
        h, p = b64(header), b64(payload)
        sig = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        return f"{h}.{p}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"

    def detect(self) -> List[ZeroDayFinding]:
        findings: List[ZeroDayFinding] = []
        resp = _safe_get(self.session, self.target)
        if not resp: return findings
        for token in self._extract_jwts(resp):
            parts = token.split(".")
            if len(parts) != 3: continue
            header = self._decode_part(parts[0])
            payload = self._decode_part(parts[1])
            alg = header.get("alg", "")
            # None algorithm bypass
            none_token = self._forge_none(header, payload)
            test_resp = _safe_get(self.session, self.target, headers={"Authorization": f"Bearer {none_token}"})
            if test_resp and test_resp.status_code == 200:
                findings.append(ZeroDayFinding(
                    id=_gen_id(), scan_id=self.scan_id, target=self.target,
                    vuln_type="JWT_NONE_ALGORITHM", severity="CRITICAL", cvss_score=9.8,
                    title="JWT 'none' Algorithm Bypass",
                    description="The server accepted a JWT with `alg: none`, allowing unsigned tokens to authenticate any user.",
                    reproduction=f"1. Decode JWT. 2. Set `alg: none`, remove signature. 3. Send as Bearer token. 4. Observe 200 OK.",
                    remediation="Explicitly whitelist allowed algorithms. Reject `none` algorithm in JWT libraries.",
                    cve_refs=["CVE-2015-9235"], evidence={"original_alg": alg, "token_snippet": token[:40]},
                    tags=["jwt", "auth-bypass", "critical"], discovered_at=_now(),
                ))
            # Weak secret brute force
            for secret in JWT_COMMON_SECRETS:
                forged = self._forge_hs256({"alg": "HS256", "typ": "JWT"}, payload, secret)
                test2 = _safe_get(self.session, self.target, headers={"Authorization": f"Bearer {forged}"})
                if test2 and test2.status_code == 200:
                    findings.append(ZeroDayFinding(
                        id=_gen_id(), scan_id=self.scan_id, target=self.target,
                        vuln_type="JWT_WEAK_SECRET", severity="CRITICAL", cvss_score=9.1,
                        title=f"JWT Signed with Weak Secret (`{secret}`)",
                        description=f"JWT was re-signed with common secret `{secret}` and accepted by the server.",
                        reproduction=f"1. Decode JWT payload. 2. Re-sign with HMAC-SHA256 using `{secret}`. 3. Send forged token.",
                        remediation="Use a cryptographically random secret of at least 256 bits. Rotate compromised secrets immediately.",
                        cve_refs=[], evidence={"cracked_secret": secret},
                        tags=["jwt", "weak-secret"], discovered_at=_now(),
                    ))
                    break
        return findings


# ═══════════════════════════════════════════════════════════
#  Orchestrator
# ═══════════════════════════════════════════════════════════

class ZeroDayHunter:
    """
    Orchestrates all zero-day detection modules for a target URL.
    Optionally uses AERIS's AI engine to generate LLM analysis per finding.
    """

    def __init__(self, ai_engine=None):
        self._ai = ai_engine

    def run(self, target: str, scan_id: str = None, urls: List[str] = None,
            enable_smuggling: bool = True, enable_ssti: bool = True,
            enable_prototype: bool = True, enable_cache: bool = True,
            enable_jwt: bool = True) -> Dict[str, Any]:
        """Run all enabled modules against target. Returns structured results."""
        if not scan_id:
            scan_id = f"aeris-{int(time.time())}"
        urls = urls or [target]
        session = _make_session()
        all_findings: List[ZeroDayFinding] = []

        if enable_smuggling:
            try:
                det = HTTPSmugglingDetector(target, scan_id)
                all_findings.extend(det.detect())
            except Exception as exc:
                logger.warning("Smuggling detection failed: %s", exc)

        if enable_ssti:
            try:
                det = SSTIDetector(target, scan_id, session)
                all_findings.extend(det.detect(urls))
            except Exception as exc:
                logger.warning("SSTI detection failed: %s", exc)

        if enable_prototype:
            try:
                det = PrototypePollutionDetector(target, scan_id, session)
                all_findings.extend(det.detect(urls))
            except Exception as exc:
                logger.warning("Prototype pollution detection failed: %s", exc)

        if enable_cache:
            try:
                det = CachePoisoningDetector(target, scan_id, session)
                all_findings.extend(det.detect())
            except Exception as exc:
                logger.warning("Cache poisoning detection failed: %s", exc)

        if enable_jwt:
            try:
                det = JWTAnalyzer(target, scan_id, session)
                all_findings.extend(det.detect())
            except Exception as exc:
                logger.warning("JWT analysis failed: %s", exc)

        findings_dicts = [f.to_dict() for f in all_findings]
        sev_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in all_findings:
            sev_counts[f.severity.upper()] = sev_counts.get(f.severity.upper(), 0) + 1

        return {
            "scan_id": scan_id,
            "target": target,
            "scanned_at": _now(),
            "total_findings": len(all_findings),
            "severity_counts": sev_counts,
            "findings": findings_dicts,
            "modules_run": [
                m for m, en in [
                    ("http_smuggling", enable_smuggling), ("ssti", enable_ssti),
                    ("prototype_pollution", enable_prototype),
                    ("cache_poisoning", enable_cache), ("jwt_analysis", enable_jwt),
                ] if en
            ],
        }

    async def run_async(self, target: str, scan_id: str = None, urls: List[str] = None,
                        **kwargs) -> Dict[str, Any]:
        """Async wrapper — runs detection then optionally enriches with AI."""
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self.run(target, scan_id, urls, **kwargs))
        if self._ai and result["findings"]:
            try:
                result["ai_summary"] = await self._ai_summary(result)
            except Exception as exc:
                logger.debug("AI summary failed: %s", exc)
        return result

    async def _ai_summary(self, result: Dict) -> str:
        if not self._ai: return ""
        findings_brief = json.dumps([
            {"type": f["vuln_type"], "severity": f["severity"], "title": f["title"]}
            for f in result["findings"][:10]
        ], indent=2)
        prompt = (
            f"You are AERIS, an expert security AI. Summarize these zero-day scan results.\n\n"
            f"Target: {result['target']}\n"
            f"Total findings: {result['total_findings']}\n"
            f"Severity breakdown: {result['severity_counts']}\n\n"
            f"Findings:\n{findings_brief}\n\n"
            "Write a 3-4 sentence technical summary of the risk exposure, most critical issues, "
            "and immediate remediation priority. Be direct and technical. No markdown."
        )
        try:
            return (await self._ai.reason(prompt)).strip()
        except Exception:
            return ""


_instance: Optional[ZeroDayHunter] = None


def get_zeroday_hunter() -> ZeroDayHunter:
    global _instance
    if _instance is None:
        from ai_engine import ai_engine
        _instance = ZeroDayHunter(ai_engine=ai_engine)
    return _instance
