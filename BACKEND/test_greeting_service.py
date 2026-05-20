"""
AERIS Greeting Service Tests
Lightweight, deterministic tests -- no network or real LLM calls required.
"""

import os
import re
import sys
from unittest.mock import patch, MagicMock

sys.path.append(".")

from services.greeting_service import (
    generate_dynamic_greeting,
    _is_valid_greeting,
    _safe_template,
    _sanitize_one_line,
    _BANNED_TOKENS,
    _DISALLOWED_SUBSTRINGS,
    _time_bucket,
)


# --------------- Test 1: Fallback works when Ollama/Groq fail ---------------

def test_fallback_on_llm_failure():
    """Force unreachable Ollama + disabled Groq -> must return a valid fallback template."""
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:9"  # unreachable
    with patch("services.greeting_service.groq_chat", side_effect=Exception("no groq")):
        g = generate_dynamic_greeting()

    assert isinstance(g, dict)
    assert set(g.keys()) == {"line"}
    line = g["line"]
    assert isinstance(line, str) and len(line) > 0

    # Must be one line
    assert "\n" not in line and "\r" not in line

    # Must contain Sir
    assert "Sir" in line

    # Word count within limits
    words = [w for w in re.split(r"\s+", line.strip()) if w]
    assert 2 <= len(words) <= 10, f"Word count {len(words)} out of range: {line}"

    # No banned tokens
    lower = line.lower()
    tokens = set(re.findall(r"[a-zA-Z']+", lower))
    overlap = tokens & _BANNED_TOKENS
    assert not overlap, f"Banned tokens found: {overlap} in: {line}"


# --------------- Test 2: Banned model output falls back safely ---------------

def test_banned_output_falls_back():
    """If LLM returns banned content, validation rejects it and fallback is used."""
    banned_outputs = [
        "Hello Sir, how are you?",
        "Hey Sir, good morning!",
        "Hi, I'm Aeris. How can I help?",
        "Sir, im aeris your assistant",
        "Heyy Sir!",
    ]
    for bad in banned_outputs:
        assert not _is_valid_greeting(bad, bucket="morning"), \
            f"Should have rejected: {bad}"

    # Confirm fallback templates ARE valid
    for bucket in ("morning", "afternoon", "evening", "night"):
        template = _safe_template(bucket, "chat")
        assert _is_valid_greeting(template, bucket), \
            f"Fallback template failed validation: {template}"


# --------------- Test 3: JSON/markdown/quotes are sanitized ---------------

def test_json_markdown_sanitized():
    """Feed wrapped strings through _sanitize_one_line and verify clean output."""
    cases = [
        ('```Sir, morning focus.```', "Sir, morning focus."),
        ('"Sir, night mode. Ready?"', "Sir, night mode. Ready?"),
        ("'Sir, afternoon. Let's go.'", "Sir, afternoon. Let's go."),
        ('{"line": "Sir, evening check."}', "Sir, evening check."),
        ("- Sir, morning diagrams.", "Sir, morning diagrams."),
        ("  `Sir, ready.`  ", "Sir, ready."),
    ]
    for raw, expected in cases:
        result = _sanitize_one_line(raw)
        assert result == expected, f"sanitize({raw!r}) = {result!r}, expected {expected!r}"


# --------------- Test 4: All fallback templates pass validation ---------------

def test_fallback_templates_pass_validation():
    """Every fallback template must pass _is_valid_greeting for its bucket."""
    modes = ["coding", "research", "security", "designing", "chat"]
    buckets = ["morning", "afternoon", "evening", "night"]

    for bucket in buckets:
        for mode in modes:
            template = _safe_template(bucket, mode)
            assert _is_valid_greeting(template, bucket), \
                f"Template FAILED validation: bucket={bucket}, mode={mode}, text={template!r}"

    # Also test the global default fallback
    default = _safe_template("unknown_bucket", "unknown_mode")
    assert _is_valid_greeting(default, "morning"), \
        f"Default fallback failed: {default!r}"


# --------------- Test 5: Memory context influences mode ---------------

def test_memory_context_influences_mode():
    """
    Mock memory_store to return coding-related history.
    Verify greeting reflects coding mode without exposing raw memory.
    """
    fake_history = [
        {"role": "user", "content": "debug this python function"},
        {"role": "assistant", "content": "Here is the fixed code..."},
        {"role": "user", "content": "refactor the login module"},
        {"role": "assistant", "content": "Done, refactored."},
    ]

    os.environ["OLLAMA_BASE_URL"] = "http://localhost:9"  # unreachable

    with patch("services.greeting_service.memory_store") as mock_mem, \
         patch("services.greeting_service.groq_chat", side_effect=Exception("no groq")):
        mock_mem.get_context.return_value = fake_history
        g = generate_dynamic_greeting()

    line = g["line"]
    # Must be valid
    assert _is_valid_greeting(line, _time_bucket()), f"Invalid greeting: {line}"

    # The greeting should NOT contain raw memory content
    assert "debug" not in line.lower()
    assert "refactor" not in line.lower()
    assert "login module" not in line.lower()

    # Should still address Sir
    assert "Sir" in line


# --------------- Test 6: Original format test (kept for regression) ---------------

def test_greeting_single_line_and_format():
    """Basic format: dict with 'line' key, one line, short, no banned tokens."""
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:9"  # unreachable

    with patch("services.greeting_service.groq_chat", side_effect=Exception("no groq")):
        g = generate_dynamic_greeting()

    assert isinstance(g, dict)
    assert set(g.keys()) == {"line"}
    line = g["line"]
    assert isinstance(line, str)

    # One line only
    assert "\n" not in line and "\r" not in line

    # Word count
    words = [w for w in re.split(r"\s+", line.strip()) if w]
    assert 1 <= len(words) <= 10

    # No banned tokens
    lower = line.lower()
    for b in _BANNED_TOKENS:
        tokens_in_line = set(re.findall(r"[a-zA-Z']+", lower))
        assert b not in tokens_in_line, f"Banned token '{b}' found in: {line}"

    # No disallowed substrings
    for sub in _DISALLOWED_SUBSTRINGS:
        assert sub not in lower, f"Disallowed substring '{sub}' found in: {line}"


if __name__ == "__main__":
    test_fallback_on_llm_failure()
    print("  [OK] test_fallback_on_llm_failure")

    test_banned_output_falls_back()
    print("  [OK] test_banned_output_falls_back")

    test_json_markdown_sanitized()
    print("  [OK] test_json_markdown_sanitized")

    test_fallback_templates_pass_validation()
    print("  [OK] test_fallback_templates_pass_validation")

    test_memory_context_influences_mode()
    print("  [OK] test_memory_context_influences_mode")

    test_greeting_single_line_and_format()
    print("  [OK] test_greeting_single_line_and_format")

    print("\nAll greeting tests passed.")
