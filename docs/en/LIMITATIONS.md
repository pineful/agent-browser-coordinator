# Limits and future work

- Cooperation is required. The library cannot block direct browser calls, authenticate actor strings, enforce a read-only browser scope, or cancel an external invocation.
- One physical local SQLite DB represents one shared resource. Copies, separate containers' same-looking paths, NFS and multiple arbiters are outside the supported model.
- There is no background daemon, exact-time scheduler, messaging service, automatic owner inquiry, or automatic timeout takeover in stable 0.3.5. Lease expiry does not mean a call ended. Task content progress is not a generic proof of liveness.
- Status, tab records and saved screenshots are historical observations. APIs may list only session-visible tabs. They do not prove a full browser inventory, retained unsaved edits, a successful upload or public publication.
- Source releases exclude runtime DBs, cookies, credentials and sessions. Restore tests verify software, not a live service state. Tests use mocks/synthetic databases and do not certify any particular website.
- The current policy serializes the whole shared UI conservatively. Independent DOM/API operations on separate tabs may be possible in some backends, but that independence has **not been validated** here. No production global lock is loosened by this package.

## Roadmap, not current features

Research authenticated worker inquiries, client-owned keepalives tied to real host lifecycle/cancellation, bounded timeout handling, safe late-worker fencing, and observation-only reconciliation of unresolved calls. Experimental v0.4 work is not a deployable host watchdog and is not bundled in this stable release.

Separately investigate which tab-local operations can coexist safely with global focus, keyboard/mouse, native file pickers and page dialogs. Require adversarial concurrency and restart tests before changing ownership policy. No parallelism or collision-free guarantee is promised.

[Configuration](CONFIGURATION.md) · [Recovery](RECOVERY.md)
