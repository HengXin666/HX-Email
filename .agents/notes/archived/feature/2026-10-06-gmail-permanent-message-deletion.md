# Agent Note: Gmail messages are deleted permanently at the provider

Status: implemented

Archived: 2026-10-14

## Problem

A message deleted from the mail UI came back on the next fetch. The delete route was a
stub that returned ``success`` and a count without touching the mailbox, and the local
purge only removed it from the Gmail web UI after a full refresh, because the local
row disappeared while the provider copy stayed in ``[Gmail]/All Mail`` and Trash.

Every stored message also kept its IMAP UID as the only identifier, and a UID is only
meaningful inside the folder it was listed from, while the same message is listed once
per label. Nothing recorded which folder a UID belonged to, so nothing could turn a
listed message back into a provider-side delete target.

## Decision

``POST /api/v1/emails/delete`` and the new
``POST /api/v1/usable-emails/{id}/messages/delete`` delete at the provider first and
drop the local rows only for ids the provider confirmed gone (``deleted_ids``). Gmail
goes through IMAP ``UID STORE +FLAGS (\Deleted)`` followed by ``UID EXPUNGE`` in one
session; Outlook/Hotmail goes through the Graph delete (``DELETE /me/messages/{id}``,
which removes the message outright rather than moving it to Deleted Items). A failed
provider delete keeps its stored row, so the UI can never claim a message is gone while
the mailbox still has it.

Gmail's mailbox names are listed in modified UTF-7 (this account's All Mail is
``[Gmail]/&YkBnCZCuTvY-``), so the English candidates in the reader's folder table never
match; ``imap/session/mailboxes.py`` resolves special-use mailboxes from the server's own
LIST attributes, and the delete runs against All Mail - the one mailbox whose view always
holds the message - because removing a label is not deleting a message.

Gmail answers ``STORE``/``EXPUNGE`` with ``OK`` and then discards the flag while the
account's ``expungeBehavior`` is still ``archive``: measured on a live account, the flag
is gone from the very next ``FETCH`` and the uid is still listed, on the newest message.
The prune therefore re-checks the uid after expunging and reports
``gmail_flag_ignored`` with the exact setting to change, instead of reporting a success
the mailbox did not perform.

Each persisted message now records its own provider UID in
``fetched_messages.purge_uid``, and ``deletion/targets.py`` resolves the folders to
try: the stored ``folder`` when a row was found, otherwise every folder the reader
persists from (``inbox``, ``junk``, ``archive``, ``deleted``).

IMAP credentials moved to ``server/mail/imap/session/`` (``credentials``, ``oauth``,
``fetch``) so the reader and the delete path resolve hosts, proxies and XOAUTH2
credentials through one module instead of two.

Bodies larger than 256 KB are stored blank while their row keeps the provider UID,
because deletion needs the binding, not the text.

## Alternatives considered

- **Call the Gmail REST API instead of IMAP.** ``users.messages.delete`` is documented
  as immediate and permanent and would need no IMAP folder semantics. It lost on two
  verified facts: the project the stored OAuth tokens belong to answers every Gmail API
  call with ``403 Gmail API has not been used in project``, and ``users.messages.delete``
  requires the restricted ``https://mail.google.com/`` scope, which the consent screen
  this app is registered under cannot request without a verification review. IMAP works
  with the scope these accounts already granted.
- **Trust the IMAP delete and drop local rows unconditionally.** Simplest, and it makes
  the UI feel instant. It lost because Gmail reports a writable-only ``select`` failure
  when the account settings still route deleted messages to Trash, so the row would
  vanish locally while the message stayed on every other client — exactly the bug this
  change removes.
- **Keep the UID only in ``message_id`` and search every folder per delete.** No schema
  change, no migration. It lost because a per-delete scan of four folders per id is a
  network round trip per folder on every deletion, and the folder a row came from is
  already known at fetch time.
- **Store the whole raw message so deletion can be retried from local data.** Would make
  retries self-contained. It lost on storage: this instance holds tens of thousands of
  rows, and the reader only needs headers plus tokens.

## Consequences

A deletion now costs one IMAP session plus one ``SELECT`` and one ``STORE/EXPUNGE`` pair
per folder, instead of a no-op. Deleting an account-wide sweep stays a separate,
existing feature. Accounts whose Gmail IMAP settings still use the default
``expungeBehavior`` get an explicit refusal message naming the setting, rather than a
silent move to Trash.

## Testing

``server/tests/test_message_deletion.py`` pins the local contract (a confirmed id drops
its rows, a refused one keeps them) and ``server/tests/test_imap_prune.py`` pins the
provider mechanics against a fake Gmail session: the delete runs in All Mail, a discarded
flag is reported as ``gmail_flag_ignored``, and a uid the mailbox never had is refused
instead of counted as deleted. ``web/src/api/endpoints/emails.delete.test.ts`` pins the
client call. ``npm run test --prefix web`` plus ``uv run --directory server pytest`` are
what ``scripts/verify.sh`` runs.
