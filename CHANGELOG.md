# Changelog

## 0.3.4 — first public package, with pre-release security hardening

- Refuse overwriting existing dashboards, release archives and checksums; create new private files instead.
- Reject symlink paths, linked DB aliases, writable runtime parents and observed DB identity changes.
- Reject non-finite clocks/JSON, duplicate JSON keys, ambiguous revisions and unknown request fields.
- Build from an explicit source snapshot; verify artifact membership, trusted checksums, clean installation and restoration.
- Run verification children with a minimal environment and time bounds; reject optimized verification.
- Add adversarial security regressions and a single mandatory release gate.

The deployed 0.3.3 instance is not modified by this distribution. Do not mix old cached writers with a new deployment.

## 0.3.3 — tested baseline, not separately published here

- Package the tested cooperative coordinator as a Python library and CLI.
- Document installation, one shared local DB, unique request IDs, ownership checks, begin/end, fair handoff, tab retention, diagnostics, and verified recovery in English, Korean, and Japanese.
- Include offline synthetic regression tests, a mock two-worker demo, an allowlisted source release, and isolated restore verification.
- Keep automatic owner messaging/keepalive integration and tab-parallel execution out of this release. They remain research work requiring host integration and safety validation.

Release numbers identify source behavior. A source restoration does not restore a browser session or task state. Never infer an automatic live upgrade from a new package version.
