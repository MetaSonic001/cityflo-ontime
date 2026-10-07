"""Directive (a): no rider phone numbers or verbatim complaint text in any tool output."""
import re

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                                   # e-mail
    re.compile(r"(?<![\w-])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w-])"),   # Indian mobile
    re.compile(r"(?<![\w-])0\d{2,4}[\s-]?\d{6,8}(?![\w-])"),                    # landline with STD code
    re.compile(r"\d{10,}"),                                                     # any long digit run
]
MASK = "[REDACTED]"


def redact_text(s: str) -> str:
    for p in _PATTERNS:
        s = p.sub(MASK, s)
    return s


def redact(obj):
    """Recursively redact every string in a tool result."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj
