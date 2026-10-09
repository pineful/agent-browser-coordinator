# Configure one shared resource

Choose one resource boundary: for example, the desktop browser whose focus, keyboard, mouse and native dialogs are shared. All participating workers must use the **same physical local SQLite DB**, not copies or matching-looking paths in separate containers. Verify read/write visibility across workers before activation. Do not place it on NFS, a cloud-sync folder, or a network drive.

```sh
mkdir -p -m 700 runtime
ABC_DB="$(pwd -P)/runtime/example-ui.db"
```

Pass `--db "$ABC_DB"` explicitly to each command. The library does not read this variable automatically. The parent directory must already exist. Installing code never initializes a DB. Initialize **once**, only for a new resource after externally verifying that prior workers will submit no more operations and all already submitted calls have ended:

```sh
agent-browser-coordinator --db "$ABC_DB" init   --args '{"resource":"example-ui","confirmed_idle":true}'
agent-browser-coordinator --db "$ABC_DB" status
```

`confirmed_idle` is an assertion you must establish, not a check the program performs. Existing DBs are not overwritten. Missing/corrupt DBs require [recovery](RECOVERY.md); do not create another arbiter to continue.

Give every worker a distinct opaque actor label. Use new request IDs for new commands and globally unique action IDs. Actor/tab/checkpoint/evidence values are 1–120 characters from letters, digits, `_ . : / -`; do not put URLs, private content or secrets there. These labels are not authentication. Priority is 0–100; lease is 10–3600 seconds. The stable core caps continuous ownership at 1800 seconds and asks for safe handoff when another worker has waited 120 seconds or has higher effective priority. The limits do not forcibly cancel a running call.

Different machines need a separately implemented trusted parent relay. There is no remote server or transport in this package.

[Usage](USAGE.md) · [Limits](LIMITATIONS.md)

## 0.3.4 file and input checks

Use physical paths without symlink components and a runtime parent that is not writable by group/others. The DB must be a regular file without hard-link aliases. Existing dashboard files are never overwritten; choose a new snapshot filename. JSON must have unique keys, finite numeric values, and only the documented arguments. Read-only commands reject argument payloads. These checks do not authenticate worker identities.
