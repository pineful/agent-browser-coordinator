# Use ownership around every actual tool call

The CLI returns JSON and exit code 2 on rejected/invalid requests. Read `ok`, `replay`, `owner.actor`, `owner.token`, and `active`. Acquiring a queue entry is not acquiring the resource. A replayed successful begin is **not** permission to perform the tool call again.

```sh
agent-browser-coordinator --db "$ABC_DB" acquire --actor worker-a   --request acquire-a-001 --args '{"priority":20,"lease":120}'
```

When the returned owner is worker-a, copy the current token. Replace `CURRENT_TOKEN` below with that exact value, and give every new command a fresh request ID:

```sh
agent-browser-coordinator --db "$ABC_DB" begin --actor worker-a   --request begin-a-001 --args '{"token":"CURRENT_TOKEN","action":"action-a-001"}'
# Execute ONE approved, bounded real tool call only after fresh non-replay success.
agent-browser-coordinator --db "$ABC_DB" end --actor worker-a   --request end-a-001 --args '{"token":"CURRENT_TOKEN","action":"action-a-001"}'
```

Use end only when that exact tool invocation has definitely terminated, including a known failure. If launch or completion is unknown, keep the unresolved action and ask the operator to reconcile. Do not hide this uncertainty in an unconditional finally block. At every new acquisition/resume, first observe the real current screen, URL/account, target, saved state and prior result under a new begin/end; do not reuse stale handles or coordinates.

The Python API is the same protocol:

```python
from agent_browser_coordinator import Coordinator
co = Coordinator("/absolute/path/to/existing-shared.db")
snapshot = co.status()  # Read-only; never creates a missing DB.
```

Run `python examples/safe_mock_worker.py` for a complete disposable mock flow. `python examples/two_workers.py` demonstrates two workers and safe priority handoff. Neither invokes a browser.

At a verified safe point:

```sh
agent-browser-coordinator --db "$ABC_DB" yield --actor worker-a   --request yield-a-001 --args '{"token":"CURRENT_TOKEN","safe":true,"checkpoint":"resume-a-001"}'
```

Yield requeues the worker and preserves its tabs; release finishes the current hold without requeuing. Waiters use `cancel` on their own actor. Reacquire with a new token before resuming. If a lease has expired, voluntary return also requires `no_pending_ui=true` and no active call. A rejected begin is never bypassed to click a Save button.

Use `tab` for opaque working/paused/held/complete and unsaved records. Only verified complete, saved, own tabs may use close-begin → actual close → close-end. Tab records are not proof a tab still exists. `inventory complete=true` requires a real complete inventory. Browser shutdown requires empty owner/queue/tabs/active, confirmed inventory and the shutdown prepare/start/end gate. Most integrations should leave shutdown to a human/operator.

`dashboard --output status.html` writes a local read-only snapshot, not a live server. Status/dashboard polling is not a heartbeat or automatic recovery.

[Handoff/recovery](RECOVERY.md) · [Limits](LIMITATIONS.md)
