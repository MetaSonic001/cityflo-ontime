# AI Workflow Rules

## Approach
Spec-driven. `SPEC.md` holds the deterministic rules. Consequential analytical calls (D1–D11) are made
by the user, in their own words, and recorded verbatim in `decisions.jsonl` with transcript anchors.
The agent proposes; it does not make judgment calls silently. Implementation-level choices the agent makes
are tagged `[impl]` in SPEC.md and surfaced for veto.

## Scoping Rules
- Work on one feature unit at a time; prefer small, verifiable increments.
- Do not tune thresholds after seeing the ranking (D8).
- Never fabricate or paraphrase a ledger quote.

## Handling Missing Requirements
- Ambiguities go to the user as a decision with options, data, recommendation, risk, and what would flip it.
- Open questions are recorded in `progress-tracker.md`.

## Protected Files
- `data/week-2026-08-03/*` and `bundle/*`: supplied inputs, never edited.

## Before Moving to the Next Unit
1. `uv run pytest -q` passes.
2. Results are re-derived through the MCP tools.
3. `progress-tracker.md` is updated.
