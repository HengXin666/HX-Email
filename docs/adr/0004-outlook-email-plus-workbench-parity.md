# 0004 Outlook Email Plus Workbench Parity

## Status

Accepted

## Context

The reference `outlookEmailPlus` application combines Flask templates, a large browser
extension, token tooling, plugin management, mailbox reading, pool administration, and
settings in one mature codebase. This repository is a FastAPI + React rewrite with a
smaller domain model centered on usable emails.

Directly copying the reference frontend would bypass the current API and deep-module
boundaries, and it would bring in workflows whose backends do not exist here yet.

## Decision

Replicate the reference as a React workbench made of page-level workflows backed by the
current FastAPI domain: dashboard, mailbox management, verification reading, mail pool,
platform bindings, settings, plugin management, and browser-extension operations.

Where the current backend already has a real capability, the UI calls it. Where the
reference depends on missing infrastructure such as OAuth token exchange, trusted plugin
execution, or extension public API governance, the UI exposes the workflow surface and
the backend reports current local state instead of pretending the full integration exists.

## Consequences

The product has a complete navigable frontend surface for the Outlook Email Plus
workflows while preserving the rewrite architecture. Future work can deepen each tab by
adding real OAuth, plugin, external API, audit, and notification services behind the same
domain language.
