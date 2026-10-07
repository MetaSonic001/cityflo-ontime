# cityflo-ontime

An MCP server that answers Priya's question: *which routes were actually late this week, by how much,
and which three were worst*. The answer is in [DECISION.md](DECISION.md), the rules are in
[SPEC.md](SPEC.md), and the steering ledger is [decisions.jsonl](decisions.jsonl). The raw session
transcripts are in [transcript/](transcript/).

## Run
Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest -q
uv run python -m ontime.server
```

The server speaks MCP over stdio. To use it from Claude Code, the repo's `.mcp.json` registers it as
`cityflo-ontime`. Change its `--directory` value to your checkout path, then approve the server when
Claude Code prompts.

## Tools
Start with `methodology` and `data_quality_report`. Next run `route_verdicts` and `worst_routes`. For
detail, use:
- `route_detail`, `trips`
- `incidents`, `rider_impact`
- `rec114_impact`, `ops_log`
- `list_datasets`

Every result passes through PII redaction (directive (a)). Non-default thresholds are labelled
`what_if: true`.

## New data (debrief)
Drop `trips.csv` into a new folder under `data/`. Add `schedule_v2.csv`, `ops_log.txt` and
`incidents.csv` if you have them; each is optional. Then pass the folder name as `dataset` to any tool.

- **`ONTIME_DATA_ROOT`** moves the data root.
- **`ONTIME_DATASET`** sets the default dataset.

There is no arbitrary-path loading: dataset names are checked against the folders that exist.
