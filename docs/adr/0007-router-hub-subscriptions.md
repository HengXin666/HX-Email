# 0007 Router Hub: Targeted Wake-ups, Persistent Subscriptions, Async Waiting

## Status

Accepted

## Context

After contract v2 the gateway could read and send, but listening had three problems.
Every stored message bumped one process-wide `threading.Condition`, so every waiter of
every user woke and re-ran its SQL (a thundering herd). Each long-poll (`/router/wait`,
MCP `events_wait`) and each SSE connection (`/router/stream`) held a thread-pool worker
for its whole wait, so a few dozen idle consumers could starve the API. And there was no
persistent subscription: `router_routes` existed in the schema with no code, so a
consumer that restarted had to keep its own cursor, and nothing on the server knew who
was listening to what.

## Decision

- Add `server/hub/`. `bus.py` keeps a registry of waiters, each with a matcher built from
  its source and the instances its user owns; every store publishes `Hit(instance_id,
chat_id, direction)` and only matching waiters wake. Matchers may over-match, never
  under-match; the database stays the source of truth and a woken waiter re-reads by
  cursor.
- `consume.py` makes every wait a coroutine: register the waiter, read once in a worker
  thread, then sleep on an `asyncio.Event` woken through `call_soon_threadsafe`. REST
  `/wait`, `/stream`, the subscription routes, and MCP `events_wait` /
  `subscription_wait` all use it; MCP routes hub tools to the coroutine path instead of
  the thread pool.
- `subscriptions.py` gives `router_routes` its CRUD: source (v1 or v2), a filter on the
  Event v2 view, a monotonic `ack_cursor`, `active`/`paused`, a per-account cap of 50.
  Long-poll does not move the ack (at-least-once); SSE can auto-ack.
- The web console gets a "消息订阅" page: create, pause, delete, live tail over SSE, ack,
  router key management, and copy-paste snippets (cURL, Python, SSE, MCP config).

## Consequences

- Idle listening costs one coroutine and one set entry per consumer, and a message wakes
  only the consumers it concerns.
- The hub is in-process. A second server process would need the same publish over a
  shared channel; until then the gateway runs as one process, as it already must for the
  single dispatcher thread.
- Webhook and WebSocket delivery (stage 3) and MCP resource notifications (stage 7) attach
  to the same subscription rows and the same publish call.
