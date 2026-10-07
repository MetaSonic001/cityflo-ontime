# Code Standards
- Keep analysis pure and separate from the MCP layer.
- Every rule cites its decision id (D1–D11) or `[impl]` and matches SPEC.md.
- Tool outputs: JSON-serialisable dicts with dataset name and params echoed.
- Tests: `tests/test_analysis.py`. Cover rules and debrief-readiness, not coverage numbers.
