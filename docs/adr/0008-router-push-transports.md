# 0008 Router Push Transports: Signed Webhooks and a WebSocket Feed

## Status

Accepted

## Context

Stage 2 made subscriptions persistent but pull-only: a consumer long-polls or keeps an
SSE stream open and acks with a separate POST. Consumers without a resident process
(serverless functions, third-party services) can only be called back over HTTP, and
browser or agent frameworks often want one bidirectional socket. The outbox already
had `kind='webhook'` rows, per-route serial claiming and restart requeue, but nothing
produced those rows and the dispatcher failed them on sight. `envelope.py` and
`impl/reader.py` were both at the 300 line ceiling in full directories.

## Decision

- Split `server/router/envelope.py` and `server/router/impl/reader.py` into packages
  that re-export every old name, so no import path changes.
- A subscription's `delivery` is `pull` or `webhook`. Webhook URL and secret are
  encrypted in `router_routes.target_encrypted`; the secret is returned once. A new
  `push_cursor` tracks what has been queued, separate from `ack_cursor`.
- `server/push/webhook_feed.py` registers one hub waiter per active webhook
  subscription and turns new, filter-accepted messages into batches of at most 50 in
  `router_outbox`. The dispatcher hands webhook rows to a 4-thread pool; one batch per
  subscription is in flight, signed with HMAC-SHA256 of the body. A 2xx moves the ack;
  failures back off from 10 s doubling to 1 h with jitter until 24 h, then `dead`.
  Paused subscriptions park due batches as `held`. Dead batches can be redelivered.
- `/router/subscriptions/{id}/ws` serves the same feed as SSE and accepts `ack` frames.
  Browsers pass the token as the subprotocol `bearer.<token>`.
- The subscriptions page can create webhook subscriptions, show the secret once, test,
  rotate, inspect and redeliver, and watch live over WebSocket or SSE.

## Consequences

- Three transports share one subscription row and one ack: pull (long-poll, SSE,
  WebSocket) and push (webhook). Delivery is at-least-once everywhere.
- Feeder, dispatcher and hub are in-process; the gateway remains single-process.
- Webhook URLs are not checked against private address ranges; a multi-tenant
  deployment needs SSRF protection before exposing webhook creation to untrusted users.
