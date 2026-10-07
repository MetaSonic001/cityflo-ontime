# Progress Tracker

## Current Phase
- Submission artifacts complete and validated. Waiting for the user to publish the repo and submit.

## Completed
- Discovery and data profiling (session 1, turn 1 response).
- User decisions D1–D11 (session 1, turn 2) plus clarifications and overrules (session 1, turn 3).
- SPEC.md, the `ontime/` server (11 tools), tests (11 passing, including an independent recompute).
- Session 2: analysis driven through the natively loaded `cityflo-ontime` MCP tools, then the
  adversarial review and threshold sensitivity (what-if runs).
- Methodology frozen (session 2, turn 3).
- Submission artifacts:
  - DECISION.md, decisions.jsonl (23 records, every quote verified verbatim at its anchor)
  - README.md run note
  - transcript/ (redacted raw logs plus redact_transcript.py)

## Next Up
- Re-export transcript/session-2 after the session ends, so it includes the final turn:
  `uv run python transcript/redact_transcript.py <~/.claude/.../7b7ae91d-….jsonl> transcript/session-2_7b7ae91d.jsonl`
- Publish a public repo. Submit through the careers connector (`get_session_log_upload_url`,
  `submit_assignment`).

## Open Questions
- None blocking. The [impl] choices (15-min incident threshold, missing tz_offset → exclude) were
  approved by the user in session 1, turn 3.

## Architecture Decisions
- No load_data(path): datasets are named folders under a configured root (user correction, turn 2).

## Session Notes
- The careers MCP connector (submission tools) is not loaded in the analysis sessions.
- Its bearer token was printed once in session 1 (line 316). The exported transcript redacts it.
- Directive (a) applies to transcripts too: session 1 lines 61/120 had complaint text, which is
  redacted in the export.
