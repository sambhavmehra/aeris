from __future__ import annotations

import datetime
import os
import re
from typing import Optional

import requests

from services.chat_engine import chat as groq_chat
from memory.store import memory_store


def _time_bucket(now: Optional[datetime.datetime] = None) -> str:
    now = now or datetime.datetime.now()
    h = now.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 21:
        return "evening"
    return "night"


def _ollama_generate(prompt: str, model: str) -> str:
    """
    Ollama direct call (local):
    POST http://localhost:11434/api/generate
    """
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/generate"
    resp = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "12")),
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("response") or "").strip()


# Canonical banned tokens -- used by both validation and tests.
_BANNED_TOKENS = {"hi", "hello", "hey", "heyy", "aeris", "im", "i'm"}

# Phrases that must never appear in output (case-insensitive).
_DISALLOWED_SUBSTRINGS = [
    "i'm aeris",
    "im aeris",
    "i am aeris",
    "hi i'm aeris",
]


def _sanitize_one_line(text: str) -> str:
    line = (text or "").strip()

    # Remove common wrapper tokens (quotes/markdown/backticks/bullets)
    line = line.strip("` \n\r\t")
    if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
        line = line[1:-1].strip()

    # Strip markdown/code fences anywhere
    line = line.replace("```", "").strip()

    # Drop leading bullets/dashes
    line = re.sub(r"^\s*[-\u2022]\s*", "", line)

    # Collapse into one line
    line = " ".join(line.splitlines()).strip()

    # Strip emojis (broad unicode ranges; keep it conservative)
    line = re.sub(
        r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]+",
        "",
        line,
    ).strip()

    # Strip JSON fragments if any
    if line.startswith("{") and "}" in line:
        m = re.search(r'"\s*line"\s*:\s*"([^"]+)"', line, flags=re.IGNORECASE)
        if m:
            line = m.group(1).strip()

    # Final collapse
    line = " ".join(line.split()).strip()
    return line


def _extract_context_signals() -> dict[str, str]:
    """
    Extract compact signals from chat history for greeting personalization.
    Do NOT return raw memory.
    """
    try:
        last_msgs = memory_store.get_context(8)
        full = " ".join((m.get("content") or "") for m in last_msgs[-4:]).lower()

        if any(w in full for w in ["debug", "bug", "fix this code", "refactor", "python mein", "code likho", "write code"]):
            mode = "coding"
            last_task = "coding"
        elif any(w in full for w in ["research", "investigate", "compare", "analyze", "paper", "thesis"]):
            mode = "research"
            last_task = "research"
        elif any(w in full for w in ["scan", "recon", "vapt", "ssl", "nmap", "whois", "dns", "vulnerability"]):
            mode = "security"
            last_task = "security"
        elif any(w in full for w in ["diagram", "flowchart", "architecture", "chart", "widget"]):
            mode = "designing"
            last_task = "diagram"
        else:
            mode = "chat"
            last_task = "general"

        project = "AERIS"
        for token in ["BACKEND/", "frontend/", "FRONTEND/", "backend/", "memory/", "rag", "neural", "brain", "tools"]:
            if token in full:
                project = token.strip("/").upper()
                break

        return {"last_task": last_task, "mode": mode, "project": project}
    except Exception:
        return {"last_task": "general", "mode": "chat", "project": "AERIS"}


def _is_valid_greeting(line: str, bucket: str) -> bool:
    """Validate a greeting line against all rules."""
    if not line:
        return False
    if "\n" in line or "\r" in line:
        return False
    if len(line) > 120:
        return False

    # Must address Sir
    if not re.search(r"\bSir\b", line):
        return False

    # Word count: 2 to 10 (accommodates fallback templates)
    words = [w for w in re.split(r"\s+", line.strip()) if w]
    if not (2 <= len(words) <= 10):
        return False

    lower = line.lower()

    # Reject disallowed phrases
    for sub in _DISALLOWED_SUBSTRINGS:
        if sub in lower:
            return False

    # Reject banned tokens
    tokens = set(re.findall(r"[a-zA-Z']+", lower))
    if tokens & _BANNED_TOKENS:
        return False

    return True


def _safe_template(bucket: str, mode: str, hacker_mode: bool = False) -> str:
    if hacker_mode:
        templates = {
            "morning": {
                "coding": "Sir, morning security code. Let's patch.",
                "research": "Sir, morning OSINT sweep.",
                "security": "Sir, morning recon. Mainframes scan ready.",
                "designing": "Sir, morning attack surface map.",
                "chat": "Sir, morning uplink. Ready for penetration test?",
            },
            "afternoon": {
                "coding": "Sir, afternoon shell execution. Build payloads.",
                "research": "Sir, afternoon darknet intel research.",
                "security": "Sir, afternoon security audit. Scan target?",
                "designing": "Sir, afternoon network diagram mapping.",
                "chat": "Sir, afternoon breach simulations ready.",
            },
            "evening": {
                "coding": "Sir, evening vulnerability patching. Audit code.",
                "research": "Sir, evening OSINT intelligence harvesting.",
                "security": "Sir, evening cyber defense scan active.",
                "designing": "Sir, evening attack vector modeling.",
                "chat": "Sir, evening terminal session secured.",
            },
            "night": {
                "coding": "Sir, night buffer overflow tests. Deploy.",
                "research": "Sir, night recon intel parsing.",
                "security": "Sir, night sweep. System intrusion checks.",
                "designing": "Sir, night security topology mapping.",
                "chat": "Sir, night watch. Intrusion detection active.",
            },
        }
        return templates.get(bucket, {}).get(mode, "Sir, secure link established. What target?")

    templates = {
        "morning": {
            "coding": "Sir, morning coding. Let's ship.",
            "research": "Sir, morning research mode.",
            "security": "Sir, morning security checks. Ready?",
            "designing": "Sir, morning diagrams. Let's map it.",
            "chat": "Sir, morning focus. What now?",
        },
        "afternoon": {
            "coding": "Sir, afternoon momentum. Let's build.",
            "research": "Sir, afternoon research. Compare and decide?",
            "security": "Sir, afternoon security. Where do we start?",
            "designing": "Sir, afternoon diagrams. Want a flow?",
            "chat": "Sir, afternoon. Let's go.",
        },
        "evening": {
            "coding": "Sir, evening unwind. Refactor and finish?",
            "research": "Sir, evening research. Summarize and act.",
            "security": "Sir, evening security. Validate findings?",
            "designing": "Sir, evening diagrams. Tighten the architecture.",
            "chat": "Sir, evening unwind. What next?",
        },
        "night": {
            "coding": "Sir, night mode. Deploy carefully.",
            "research": "Sir, night mode. Synthesize your plan.",
            "security": "Sir, night mode. Last run - check risks.",
            "designing": "Sir, night mode. Finalize the chart.",
            "chat": "Sir, night mode. Ready?",
        },
    }
    return templates.get(bucket, {}).get(mode, "Sir, ready. What now?")


def generate_dynamic_greeting() -> dict[str, str]:
    """
    Returns: {"line": "<greeting>"} (single short line).

    Rules:
    - 1 line only
    - No quotes/markdown/emojis
    - Must NOT include: hi, hello, hey, heyy, aeris, im, i'm, or self-intro
    - Address politely using "Sir"
    - Keep it professional, short (max 10 words)
    """
    bucket = _time_bucket()
    now = datetime.datetime.now().strftime("%H:%M")
    signals = _extract_context_signals()
    last_task = signals.get("last_task", "general")
    mode = signals.get("mode", "chat")

    from memory.user_profile import user_profile_store
    hacker_mode_active = user_profile_store.get_profile().get("hacker_mode", False)

    if hacker_mode_active:
        prompt = f"""You are AERIS security greeting generator.
Task: create ONE short hacker/cybersecurity-themed greeting line, time-aware for: {bucket}.
Current time (for reference): {now}

Personalization hints (use subtly, NOT as raw text):
- last task type: {last_task}
- mode: {mode} (Hacker Mode is ACTIVE)
- project hint: {signals.get("project","AERIS")}

Constraints (must follow exactly):
- Output ONLY the greeting line. No JSON, no markdown, no quotes.
- Length: 2 to 10 words max.
- MUST NOT contain these words/phrases (case-insensitive):
  hi, hello, hey, heyy, i'm, im, aeris, "i am aeris", "im aeris".
- Should address Sir politely (use "Sir" exactly).
- It should feel cybersecurity, OSINT, or hacker-focused: "cyber recon active", "terminal secure", "security link established", "threat audit ready" etc.

Examples (do NOT copy verbatim):
- "Sir, morning security sweep. Target ready?"
- "Sir, afternoon recon. Cyber vectors aligned."
- "Sir, evening terminal secured. Status green."
- "Sir, night watch. Intrusion detection active."
"""
    else:
        prompt = f"""You are AERIS greeting generator.
Task: create ONE short greeting line, time-aware for: {bucket}.
Current time (for reference): {now}

Personalization hints (use subtly, NOT as raw text):
- last task type: {last_task}
- mode: {mode}
- project hint: {signals.get("project","AERIS")}

Constraints (must follow exactly):
- Output ONLY the greeting line. No JSON, no markdown, no quotes.
- Length: 2 to 10 words max.
- MUST NOT contain these words/phrases (case-insensitive):
  hi, hello, hey, heyy, i'm, im, aeris, "i am aeris", "im aeris".
- Should address Sir politely and professionally (use "Sir" exactly).
- It should feel like: "morning focus", "afternoon momentum", "evening unwind", "night mode" etc.

Examples (do NOT copy verbatim):
- "Sir, morning focus. What now?"
- "Sir, afternoon momentum. Let's go."
- "Sir, evening unwind. Level up?"
- "Sir, night mode. Ready?"
"""

    ollama_model = os.getenv("OLLAMA_MODEL", "llama3")

    raw_text = ""
    try:
        raw_text = _ollama_generate(prompt=prompt, model=ollama_model)
    except Exception:
        forced = prompt + "\n\nReminder: output ONLY the greeting line as plain text."
        try:
            raw_text = groq_chat(forced)
        except Exception:
            raw_text = ""

    line = _sanitize_one_line(raw_text)

    if not _is_valid_greeting(line, bucket=bucket):
        line = _safe_template(bucket=bucket, mode=mode, hacker_mode=hacker_mode_active)

    # Final sanitize (in case template contains odd whitespace)
    line = _sanitize_one_line(line)
    return {"line": line}
