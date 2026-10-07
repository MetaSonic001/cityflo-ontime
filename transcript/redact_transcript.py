"""Make the shareable copy of a raw Claude Code session transcript (.jsonl).

Only two kinds of content are removed. Everything else stays byte-for-byte, and line numbers are kept,
so anchors in decisions.jsonl still point to the right place.

1. Credentials: bearer tokens / API keys (e.g. the careers-connector token that a config inspection
   printed during session 1).
2. Directive (a): verbatim rider-complaint text from the ops log. A transcript is a trace/log too.

Usage: uv run python transcript/redact_transcript.py <src.jsonl> <dst.jsonl> [ops_log.txt]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ontime.analysis import _parse_ops_log  # noqa: E402  (same complaint classifier the tools use)

SECRET_PATTERNS = [
    re.compile(r"\bcf_(?:live|test)_[A-Za-z0-9_]+"),
    re.compile(r"(?i)(bearer\s+)(?!\[REDACTED)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"\b(?:sk-ant-|sk_live_|ghp_|gho_|github_pat_|xox[bp]-)[A-Za-z0-9_-]{10,}"),
]
TOKEN_MASK = "[REDACTED-TOKEN]"
COMPLAINT_MASK = "[REDACTED-COMPLAINT-TEXT]"


def complaint_fragments(ops_log: Path) -> list[str]:
    """Verbatim complaint text (and its first clause, which may be quoted on its own), longest first."""
    lines = ops_log.read_text(encoding="utf-8").splitlines()
    frags = set()
    for e in _parse_ops_log(ops_log):
        if e["category"] != "rider_complaint":
            continue
        body = re.split(r"\d{1,2}:\d{2}\s+", lines[e["line"] - 1], maxsplit=1)[-1].strip()
        frags.add(body)
        if len(body.split(",")[0]) >= 8:
            frags.add(body.split(",")[0])
    return sorted(frags, key=len, reverse=True)


def redact_line(line: str, frags: list[str]) -> str:
    for p in SECRET_PATTERNS:
        line = p.sub(lambda m: (m.group(1) if m.lastindex else "") + TOKEN_MASK, line)
    for f in frags:
        line = line.replace(f, COMPLAINT_MASK)
    return line


def main(src: str, dst: str, ops_log: str | None = None):
    frags = complaint_fragments(Path(ops_log or ROOT / "data" / "week-2026-08-03" / "ops_log.txt"))
    out, changed = [], 0
    for line in Path(src).read_text(encoding="utf-8").splitlines():
        new = redact_line(line, frags)
        if new != line:
            changed += 1
            json.loads(new)  # every redacted line must still be valid JSON
        out.append(new)
    Path(dst).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{Path(src).name} -> {dst}: {len(out)} lines, {changed} redacted")


if __name__ == "__main__":
    main(*sys.argv[1:])
