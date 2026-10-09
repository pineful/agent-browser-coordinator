# Use ownership around every actual tool call

## Short ownership and work classification

For adapters, `agent_browser_coordinator.guard.run_guarded` checks a fresh, non-replayed begin response with matching actor/token/action before invoking the callback. The callback returns `(terminated, value)`; exceptions and uncertain termination leave the action active for diagnosis. This prevents a participating wrapper from calling its tool after `YIELD_REQUIRED`, but cannot block calls made outside that wrapper. Mark a fresh read `kind='observation'` and a useful call `kind='work'` (the default). A resumed owner with a checkpoint gets at most two calls to finish one work action after observation before waiter aging requests another yield; two observations do not extend this bound. Lease expiry and the continuous hold ceiling still apply.

Workers may mark themselves `readiness --actor worker-a --request ready-001 --args '{"state":"preparing"}'` during off-UI preparation and later use `state=ready`. A preparing queued worker is skipped by dispatch; `status.next_ready_actor` identifies the next ready queued actor under existing FIFO/priority/aging rules, and `status.handoff_ready` signals a safe boundary where an owner should checkpoint and yield. These are status signals, not worker creation or execution guarantees. `acquire` remains ready by default for older clients.

Own the UI only for a bounded invocation: acquire, verify owner/token, begin, call one tool, end, then yield or release at a safe boundary. Document preparation, file analysis, server generation, review and publication waits belong outside UI ownership. Resume with a new token and a fresh UI observation. With a waiter, the configurable time slice (default 180 seconds) is checked at the next begin. Existing 120-second queue aging and 30-minute continuous cap remain. Active calls are never interrupted or reassigned; a cancelled waiter does not force rotation.

`heartbeat` records manual worker liveness only. It neither renews the lease nor proves tool progress. No automatic execution-host heartbeat bridge is included. Read `last_keep_alive_at` separately from `active` and the owner deadline.

`classify_work(kind, capability=...)` supplies a planning hint. Unknown work, shared screen/keyboard, native file choosers, modals and browser UI require exclusive sequential use. File analysis and server generation waits can run outside UI ownership. A `tab_id` alone does not prove parallel safety. A tab API is only a parallel *candidate* after adapter identity, evidence, verification, and session/input/focus/dialog isolation claims. This library neither verifies host claims nor runs parallel browser calls; keep actual UI sequential until the adapter and environment are tested.

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
