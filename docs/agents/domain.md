# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repo root.
- `docs/adr/` for architectural decisions that touch the area being changed.

This is a single-context repo unless a future `CONTEXT-MAP.md` is introduced.

## Use the glossary's vocabulary

When output names a domain concept, use the term as defined in `CONTEXT.md`. Do not drift to synonyms listed under `_Avoid_`.

## Flag ADR conflicts

If an implementation plan contradicts an existing ADR, surface the conflict explicitly before proceeding.
