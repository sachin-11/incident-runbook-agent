"""Make untrusted text (logs, deploy notes, health details) safe to hand to the model.

Every read tool passes its text through `sanitize()` before returning it:
- strips ANSI escapes, control characters (except tab and newline) and invisible/bidi characters,
- caps the length of each field, and `TextBudget` caps the total per response,
- flags instruction-like content (prompt injection) without removing it, because the text is
  still evidence for the diagnosis. The agent treats flagged text as data, never as instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MAX_CHARS = 500
DEFAULT_TOTAL_BUDGET = 8_000

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|all|earlier|"
        r"your)\b.{0,20}\b(instructions?|prompts?|rules|guidelines)\b",
        re.I | re.S,
    ),
    "role_override": re.compile(
        r"\byou are now\b|\bact as (an? )?\w+|\bnew (system )?instructions?\b|\bjailbreak\b",
        re.I,
    ),
    "prompt_markup": re.compile(
        r"<\|?\s*(system|im_start|im_end|assistant|user)\s*\|?>|^\s*(system|assistant)\s*:"
        r"|\bsystem prompt\b|\[/?INST\]",
        re.I | re.M,
    ),
    "tool_invocation": re.compile(
        r"\b(call|invoke|run|execute|use)\b.{0,30}\b(tool|function|restart_service|"
        r"get_logs|get_metrics)\b",
        re.I | re.S,
    ),
    "credential_bait": re.compile(
        r"\bapproval[_ ]?token\b|\b(api[_ ]?key|password|secret|access[_ ]?key)\s*[:=]",
        re.I,
    ),
}


@dataclass(frozen=True)
class Sanitized:
    text: str
    flags: tuple[str, ...] = ()
    truncated: bool = False


def clean(text: str) -> str:
    """Remove escapes and characters that can hide or reorder content."""
    text = _ANSI.sub("", text)
    text = _INVISIBLE.sub("", text)
    return _CONTROL.sub("", text)


def detect_injection(text: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(text))


def sanitize(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> Sanitized:
    cleaned = clean(text)
    # Detect on the full cleaned text so truncation cannot hide a payload's first half.
    flags = detect_injection(cleaned)
    if len(cleaned) <= max_chars:
        return Sanitized(cleaned, flags)
    dropped = len(cleaned) - max_chars
    return Sanitized(f"{cleaned[:max_chars]}...[truncated {dropped} chars]", flags, True)


class TextBudget:
    """Caps the total characters of text fields in one tool response."""

    def __init__(self, total: int = DEFAULT_TOTAL_BUDGET) -> None:
        self.remaining = total
        self.exhausted = False
        self.flags: set[str] = set()

    def take(self, text: str, max_chars: int = DEFAULT_MAX_CHARS) -> Sanitized | None:
        """Sanitize `text`; None once the budget is spent (caller stops adding items)."""
        if self.remaining <= 0:
            self.exhausted = True
            return None
        result = sanitize(text, min(max_chars, self.remaining))
        self.remaining -= len(result.text)
        self.flags.update(result.flags)
        return result
