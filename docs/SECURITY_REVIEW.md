# Security review and regression coverage — 0.3.5

The 0.3.4 independent review passed its 149 included tests and 12 additional adversarial checks. Version 0.3.5 incorporates those 12 checks into the repository suite (161 total), reorganizes the tooling, and reruns the complete release gate. This does not imply a new security certification.

This review is scoped to a cooperative coordinator used by trusted processes on one local filesystem. It is not a security certification. Tests do not prove the absence of every defect or enforce the behavior of a browser/server.

## Fixed before first publication

- Dashboard output could overwrite an existing file, including a mistakenly selected DB path. Output now uses exclusive creation, refuses existing/symlink paths and unsafe parents, and creates mode-0600 files.
- Non-finite clocks/JSON, duplicate JSON keys, boolean revisions and ignored extra request fields could produce ambiguous metadata or unnecessary stored payload. The public patch rejects these inputs and bounds command arguments.
- DB path aliases and observed identity changes are now rejected before transactions, including the rejection-audit path. Initialization uses exclusive creation; missing/corrupt state never triggers automatic recreation.
- Release ZIP/checksum generation previously allowed overwrite or symlink destinations. Release outputs are now new files in a trusted directory. Source reads check parent links, file identity, regular type and size, and reject observed changes.
- Restore rejects unsafe/duplicate archive names, duplicate manifest keys, links, size overflow, unsafe parents and existing destinations before extraction. It consumes the exact bytes whose SHA was checked.
- Installed-wheel checks now require a matching trusted SHA first, use a minimal subprocess environment without inherited credentials/optimization settings, and set time bounds. All release artifacts are checked against the reviewed source snapshot.

The SQL statements use parameterized values. Existing tests cover concurrent ownership, transaction failure/rollback, stale tokens, replay, interruption, diagnostic uncertainty and verified recovery. New tests cover the fixes above, including output races, file replacement, secret-payload rejection and failing release checks.

## Boundaries that remain

Actor names and fencing tokens are not authentication or secret capabilities. Another process that can read/write the same DB can claim the same actor/token. A regression explicitly demonstrates this limitation. Do not expose the raw protocol to untrusted callers; authenticate and bind worker identities in a separate trusted adapter if needed.

The library does not cancel an already submitted external call, enforce read-only browser operations, or stop code that bypasses begin/end. Never infer call termination from timeout. Ownership and permission for an external action are separate.

Use a private trusted runtime/release parent directory, without group/world write access, and physical paths without symlink components. No filesystem defense here protects against malicious code running as the same OS user or a privileged process that can replace files between every check. Observed identity-change checks reduce accidental/racing misuse; they are not a hostile-local-process sandbox.

Checksums and manifests establish byte consistency, not source authenticity. Obtain the expected SHA from a trusted release record. Restored validation scripts and installed wheels execute code: run the gate only on reviewed source and trusted artifacts. A new venv and temporary directory are not OS/VM isolation.

The secret-pattern scan covers explicit release paths and built archives; it is not exhaustive. Manually review every changed public file. No live DB, credential, session, private screenshot or private operator instruction is included. Hosted CI is a reference example and has not run automatically.

## Mandatory release command

```sh
python -m scripts.release_gate --output-dir dist/new-reviewed-release
```

The parent `dist` directory must already exist and be trusted. The output directory must not exist. Any failed functional/security test, scan, build, wheel installation or source restoration returns a nonzero exit code and does not produce a successful RELEASE_VALIDATION.json. Publish only artifacts from a completed gate, then verify the actual remote commit and artifact bytes.
