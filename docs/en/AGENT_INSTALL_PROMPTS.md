# Prompts for asking an agent to install the package

## Operational-readiness addendum to copy into an integration request

```text
Report three separate milestones: package installation verified; every real browser tool adapter connected to acquire/verify/begin/one call/end; host environment and capability isolation verified. Installation alone does not make you able to control a browser. Identify the host's persistent agent-instruction file and explicitly link this protocol without overwriting existing user instructions. If that file or adapter is inaccessible, report installation only and do not claim operational readiness.

Classify each task before execution. Unknown work, shared screen/keyboard, native file chooser, modal, and any unverified browser UI are exclusive and sequential. File analysis, document preparation, server generation, review and publication waits belong outside UI ownership and may proceed in parallel. A tab_id alone is not isolation evidence. Require tested adapter evidence for independent sessions, focus, input and dialogs before treating a tab API as a parallel candidate. Do not enable parallel browser execution without a host experiment.

Use short UI ownership: acquire, verify fresh owner/token, begin, invoke one bounded tool, end, checkpoint and yield/release at safe boundaries. A waiting worker can require yield at the next begin after the configured time slice; do not interrupt an active invocation. On interruption or restart, inspect current DB, unresolved invocations and actual browser state; acquire a new token before resuming. Keep-alive indicates worker liveness only, not tool completion or lease renewal. There is no automatic heartbeat bridge. Perform a synthetic smoke test, then an authorized read-only real-tool smoke test through the wrapper and show begin/call/end and safe return evidence. If permissions or adapter access are missing, report exactly which milestones remain unverified. Never include credentials or private deployment paths in examples.
```

Copy a sample into your agent. The first scope is isolated installation and verification. Use the second only after reviewing that result and separately choosing a real integration. The agent and host must support the required capabilities; a prompt does not establish host permissions or prove success.

Fill both hash placeholders with the 64-character values from a trusted SHA256SUMS record for this exact release. Missing values or uncertain provenance must block execution and trigger clarification. A ZIP cannot embed its own final hash in its contents; use the separate release verification record.

## 1. Request installation and verification only

```text
Install and verify Agent Browser Coordinator 0.3.5.
Repository: https://github.com/pineful/agent-browser-coordinator
Exact release: https://github.com/pineful/agent-browser-coordinator/releases/tag/v0.3.5

First check the host OS, Python version, and current filesystem, network, and software-execution permissions. Local validation used POSIX/Python 3.12; package metadata requires Python >=3.10. Check other environments and label unverified compatibility. Do not interpret this request as permission to access another computer or expand permissions.

Identify existing coordinator code, databases, and browser sessions, and preserve them. Use a new dedicated directory and separate virtual environments. Read the tagged installation, LICENSE, NOTICE, SECURITY, limitation, and recovery documents first. main can change; do not execute different source just because its version label matches.

Download these exact release assets and verify SHA-256 before execution, installation, or extraction:
agent-browser-coordinator-0.3.5-source.zip
<TRUSTED_SOURCE_ZIP_SHA256>
agent_browser_coordinator-0.3.5-py3-none-any.whl
<TRUSTED_WHEEL_SHA256>
If a hash placeholder remains, do not execute; ask for the verified value.

Establish trust in the delivery of this prompt and the release source as well. A checksum or manifest obtained alongside a download does not by itself establish authenticity. Stop and report a hash mismatch or an untrusted source. Restore source only into a new directory, rejecting symlinks, path traversal, and overwrites.

Prepare a separate tooling virtual environment for the verified source. Obtain only its declared build dependencies from the official package registry as needed within existing permissions. Choose a nonexistent output directory under a trusted parent and run python -m scripts.release_gate --output-dir <new output directory>. The gate checks security regressions, synthetic ownership/recovery, source allowlisting, artifacts, fresh installation, and source restoration. Record success only if all stages exit 0 and the success report exists. Do not skip tests or relax failure conditions.

Then install the hash-matched release wheel in a separate runtime virtual environment using --no-index --no-deps. From outside the source tree, verify the version, import, CLI, and synthetic acquire/begin/end/release sequence. Check that a missing database is not created automatically. Test databases must be temporary synthetic state only.

This scope excludes live database initialization, stopping existing workers, browser operations, external publication/upload, and installing an automatic service. Do not print or commit credentials, secret environment values, sessions, or tokens. Do not automatically create credentials, expand authentication scopes, or change security settings.

Report the actual environment, verified version/hashes, installation location, checks passed, incomplete/unverified stages, and prerequisites for integration. A download alone or a blocked test is not successful installation or operational readiness. Do not claim that the existing deployment was automatically upgraded.
```

## 2. Request a separate real integration after verification

Specify the host, shared resource, workers and actual wrappers, and allowed observation. Unfilled placeholders must trigger clarification, not an inferred live deployment.

```text
Prepare and verify integration of the previously verified Agent Browser Coordinator 0.3.5.
Host and shared UI resource: <specify>
Participating workers and actual tool wrappers: <specify>
One absolute database path shared by all participants: <specify>
Read-only UI observation allowed for verification: <specify>

First establish that every participant can actually read and write the same DB path. Inspect existing code, DB, owner, unresolved calls, and unsaved UI state. Before live initialization, require evidence that existing participants have no unresolved calls and have safely stopped or handed off. If this cannot be established, report the blocker rather than creating a replacement DB or overwriting state. Restoring source is different from reconstructing live state.

Connect and verify every wrapper that actually submits a tool call: acquire → verify current owner/token → begin → exactly one tool call → end, followed by safe release/handoff. Distinguish failure from unresolved or unknown outcomes. Use synthetic state to test stale tokens, duplicate requests, and interrupted resumption. Perform only the read-only observation specified above, after acquiring the shared resource and freshly checking the screen and target. Do not arbitrarily close another worker's unsaved editor or file picker.

A successful CLI command does not prove real UI integration. Report which wrappers are connected, matching actual calls and end records, and evidence of safe release. This is cooperative coordination, not an authentication boundary or forced block on direct UI calls. Automatic owner messaging/keepalive and parallel tab execution are not shipped capabilities. An ownership grant does not authorize external publication or transmission. Do not output secrets.
```

[Install](INSTALL.md) · [Configure](CONFIGURATION.md) · [Usage](USAGE.md) · [Recovery](RECOVERY.md) · [Limits](LIMITATIONS.md)
