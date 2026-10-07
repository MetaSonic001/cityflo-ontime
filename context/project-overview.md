# Cityflo On-Time Route Review

## Overview
An MCP server, driven by a coding agent, that answers Priya's (Ops Lead, Mumbai North) Friday question:
which routes were actually late this week, by how much, and which three were worst. The answer must survive
a review by people who lose money by it: a false LATE costs a depot head the on-time incentive; a false
clear costs the rider refund queue and app ratings. Source: `bundle/HANDOFF.md`, `bundle/BRIEF.md`.

## Goals
1. One systematic verdict per route plus a ranked worst-three, each traceable to trip ids.
2. A committed, defended decision record (`DECISION.md`) and a steering ledger (`decisions.jsonl`)
   anchored to the raw transcript.
3. A tool that can be re-driven live on a fresh data slice with a new constraint (15-min debrief).

## Core User Flow
1. Agent calls `methodology` and `data_quality_report`.
2. Agent calls `route_verdicts` and `worst_routes`.
3. Under challenge, agent drills into `route_detail`, `trips`, `incidents`, `rec114_impact`, `rider_impact`.

## Scope
### In Scope
- Python MCP server (stdio) over `data/<dataset>/` CSVs; deterministic rules in `SPEC.md`.
- Directives: (a) no rider phone / verbatim complaint text in any output; (b) REC-114, applied per D2.
### Out of Scope
- UI, cloud services, databases, LLM calls inside the server, polish.

## Success Criteria
1. Verdicts and ranking come from MCP tool calls, not manual calculation.
2. Every exclusion and every consequential call is visible by trip id.
3. No hard-coded answers; a new dataset folder works without code changes.
