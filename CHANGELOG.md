# Changelog

## 0.3.5 — repository hierarchy and reproducible review checks

- Keep the implementation only in src/agent_browser_coordinator; remove the root import shim.
- Group release tooling under scripts, examples under examples, and review regressions under tests/reviews.
- Store the release allowlist in config and security review in docs.
- Update module commands, package manifests, three-language guides, and installation prompts.
- Include the twelve additional independent artifact/input checks in the mandatory 161-test gate.
- Preserve the immutable 0.3.4 release and its artifacts; runtime behavior is unchanged apart from the reported version.

## Repository documentation update after 0.3.4

- Make Korean the default README and move the English introduction to README.en.md.
- Keep the Korean compatibility link and Japanese README, with checked language navigation.
- Add agent installation and separately scoped integration prompt samples in Korean, English, and Japanese.
- Preserve the reviewed 0.3.4 tag and release assets; this documentation update does not change runtime code.

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
