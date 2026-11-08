# 0006 Router Contract v2: Hierarchical Addresses, Event View, Declared Capabilities

## Status

Accepted

## Context

ADR 0005 fixed the session address as `<platform>:<instance_id>:<session_type>:<peer>`
and hard-coded the platform and session type sets in the router core. The gateway is now
meant to be the shared messaging layer for other services (an agent harness with
triggers and thread subscriptions), and the next platforms need nested objects: QQ guild
channels, QQ zone posts with comments, GitHub discussions and commits. With the type in
front of the peer, "everything under this repository" is not a single prefix, nested
objects would each invent a sub-syntax inside the peer, and every new platform edits core
enums. The v1 envelope also has no event kind, no thread, and no place for mention or
reply signals, which triggers need.

## Decision

- Introduce address v2, `<platform>:<instance_id>(/<kind>[/<id>])*`, whose kinds, id
  shapes and parent links are declared per platform in a capability registry
  (`server/contract/`). Prefix match is by path step.
- Keep v1 as the storage key. Every entry point accepts both forms and normalises to v1,
  so no data migration and idempotency keys stay shared across forms. Outputs add the v2
  `address` next to the v1 fields.
- Platforms and session types in the router core come from the registry instead of
  literals. `capabilities_list` exposes the declarations to MCP and REST.
- Read results gain a v2 event view (`kind`, `thread`, `parent`, `mentions`, `flags`,
  `segments`) on top of the unchanged v1 fields; flags a platform does not report are
  `null`, not `false`.

## Consequences

New platforms and new levels are a declaration plus a provider. Storage of mentions and
flags, filters on them, persistent routes and push delivery are the next stage and build
on this contract. Two address forms coexist until the frontend and callers move to v2.
