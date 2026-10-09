# Safe handoff and verified recovery

## Ordinary yield

Finish the exact in-flight tool call, retain a minimal checkpoint and unsaved state, then yield or release. A new owner must obtain fresh screen/service evidence. Never close somebody else's tab or turn an unknown upload/publish result into a failure just to retry.

File selection and server processing are different stages. A closed native picker or a short event timeout does not prove upload completion/failure. Observe the actual preview, processing state, enabled Apply/Next control, rendered result, saved state, and dialog closure within a reasonable bounded period. Do not use a universal fixed sleep or submit the same file again while the result is unknown.

## Expired or stopped owner

Stable 0.3.4 **does not automatically steal an expired hold**. Stop new submissions through the coordinating operator. Freeze first, read exact status revision/owner/shutdown token, independently establish that the old worker is quiescent and every already-submitted tool has terminated. Only then invoke recover with `verified_idle=true`, `old_worker_quiescent=true`, an opaque evidence reference, and the exact `expected_revision`, `expected_token` and `expected_shutdown_token` (null when absent). A changed revision/token is a rejection; re-inspect instead of forcing it.

```sh
agent-browser-coordinator --db "$ABC_DB" freeze --actor coordinator-operator   --request freeze-001
agent-browser-coordinator --db "$ABC_DB" status
```

The externally checked values must be supplied in recover's `--args`; there is deliberately no copy/paste command with invented true assertions. Recovery grants a new generation, preserves tab records and invalidates old ownership. It does not cancel remote actions or prove browser state.

For an unresolved action, the stable diagnostic path requires a frozen original owner/action and an operator-issued exact-revision permit. `diagnose-authorize`, original-owner `diagnose-begin/end`, and `manual-reconcile` distinguish an unknown original result from a separately verified manual result. These are cooperative read-only scopes, not browser-enforced ACLs. Read command validation and synthetic diagnostic tests before integration; do not assert terminal evidence based only on timeout.

## Lost source or DB

Restore trusted source into a **new empty directory**. Run `verify_backup.py ARCHIVE --sha256 EXPECTED_SHA256 --destination NEW_DIRECTORY`; the hash must come from a trusted release record. Verification checks the exact allowlist and member hashes before extraction and runs isolated synthetic tests. Existing destinations are refused. No runtime DB is included or activated.

If the original DB is intact, retain it; a new source checkout is not a new resource. Never copy/replace active DB/WAL/SHM files. If state is missing or untrustworthy, stop all known writers and drain real calls before an explicit fresh DB/epoch decision. Begin with unknown inventory, discard every old token, inspect actual screens/results once through the new gate, then allow workers to reacquire. Software recovery is not browser/session recovery.

[Limits](LIMITATIONS.md) · [Usage](USAGE.md)

A checksum is not source authentication. Restore runs code from the archive: use only trusted releases and a new destination under a private trusted parent (for example, inside a newly created private temporary directory). Symlink parents and existing outputs are refused.
