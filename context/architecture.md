# Architecture Context

## Stack
| Layer | Technology | Role |
|---|---|---|
| Server | Python 3.12, `mcp` 2.x `MCPServer` (stdio) | tool surface for the agent |
| Analysis | pandas, numpy | deterministic rules from SPEC.md |
| Env | uv | `uv run python -m ontime.server` |

## System Boundaries
- `ontime/analysis.py`: loading, validity rules, lateness, metrics, ranking, bootstrap, REC-114. No MCP code.
- `ontime/server.py`: thin MCP tools; every result passes through `redact()`.
- `ontime/redact.py`: directive (a).
- `data/<dataset>/`: one folder per data slice (configured root `ONTIME_DATA_ROOT`, default `./data`).

## Storage Model
- Files only. No database. In-process cache keyed by file mtimes.

## Invariants
1. Tools accept a dataset *name* validated against existing folders under the data root; never a path.
2. Every tool output is redacted; only whitelisted trip columns are loaded; complaint text is never returned.
3. Ops-log/incident context never changes a number.
4. REC-114 revised runtime applies only to identifiably-4xx trips.
5. Same input gives the same output (seeded bootstrap, deterministic sort).
