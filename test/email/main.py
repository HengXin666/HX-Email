"""Minimal test entry point — one-shot fetch with a `----` delimited credential string.

Usage:
    # One-shot (recommended):
    uv run test/email/main.py -v 'email----password----client_id----refresh_token'

    # Or with individual flags:
    uv run test/email/main.py -v --client-id ... --refresh-token ... --email ...

The `----` credential format mirrors the reference project's account import format:
    email ---- password ---- client_id ---- refresh_token
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from project root without installing the package
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from test.email.email_fetcher import (  # noqa: E402 — sys.path setup above
    EmailItem,
    FetchResult,
    fetch_emails,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  DEFAULTS — used when no CLI args are provided
# ═══════════════════════════════════════════════════════════════════════════════

# One-shot credential string: email----password----client_id----refresh_token
CONN_STRING: str = ""

# Which folder to read (inbox, junkemail, deleteditems, sentitems, drafts, archive).
FOLDER: str = "inbox"

# Pagination: skip N messages, return up to TOP messages.
SKIP: int = 0
TOP: int = 20

# Skip Graph API and go directly to IMAP (useful when Graph API is not enabled).
USE_IMAP_ONLY: bool = False

# ═══════════════════════════════════════════════════════════════════════════════


def _parse_conn(raw: str) -> tuple[str, str, str, str]:
    """Parse `email----password----client_id----refresh_token` into 4 fields.

    Trailing `$$` on the refresh_token (Microsoft token sentinel) is stripped.
    """
    parts: list[str] = raw.split("----")
    if len(parts) != 4:
        expected: list[str] = ["email", "password", "client_id", "refresh_token"]
        got: str = (
            " | ".join(
                f"{exp}={parts[i] if i < len(parts) else '(missing)'}"
                for i, exp in enumerate(expected)
            )
            or f"raw len={len(parts)}"
        )
        raise SystemExit(
            "❌ Expected 4 `----`-separated fields: "
            "email----password----client_id----refresh_token\n"
            f"   Got {len(parts)} fields: {got}"
        )
    email_addr, password, client_id, refresh_token = parts
    # Strip trailing $$ (Microsoft token format sentinel)
    refresh_token = refresh_token.rstrip("$")
    return email_addr.strip(), password.strip(), client_id.strip(), refresh_token.strip()


def _print_email(item: EmailItem, idx: int) -> None:
    """Pretty-print a single email to the terminal."""
    read_mark: str = " " if item.is_read else "●"
    attach_mark: str = "📎" if item.has_attachments else " "
    print(f"\n{'─' * 70}")
    print(f"  [{idx}] {read_mark} {attach_mark}  {item.subject}")
    print(f"  From: {item.from_address}")
    print(f"  Date: {item.date}")
    print(f"  ID:   {item.id}")
    if item.body_preview:
        preview: str = item.body_preview.replace("\n", " ")[:120]
        print(f"  Body: {preview}")


def _print_result(result: FetchResult) -> None:
    """Pretty-print a FetchResult."""
    if not result.success:
        print(f"\n❌ Fetch failed: {result.error}")
        return

    print(f"\n✅ Method: {result.method}")
    print(f"   Emails: {len(result.emails)}")
    print(f"   Has more: {result.has_more}")

    for idx, em in enumerate(result.emails, start=1):
        _print_email(em, idx)

    print(f"\n{'─' * 70}")
    print(f"Total: {len(result.emails)} emails via {result.method}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Minimal email fetch test — Graph API → IMAP fallback",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # One-shot with credential string (single-quote to protect $ signs):
  uv run test/email/main.py -v 'email----password----client_id----refresh_token'

  # Individual flags:
  uv run test/email/main.py -v --client-id ID --refresh-token RT --email E

  # JSON output:
  uv run test/email/main.py --json 'email----password----client_id----refresh_token'
""",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of pretty-print"
    )
    parser.add_argument("--client-id", default="", help="Azure AD client_id")
    parser.add_argument("--refresh-token", default="", help="OAuth2 refresh_token")
    parser.add_argument("--email", default="", help="Email address to fetch")
    parser.add_argument("--folder", default=FOLDER, help="Mail folder name")
    parser.add_argument("--skip", type=int, default=SKIP, help="Skip N messages")
    parser.add_argument("--top", type=int, default=TOP, help="Return up to TOP messages")
    parser.add_argument(
        "--imap-only",
        action="store_true",
        default=USE_IMAP_ONLY,
        help="Skip Graph API, use IMAP directly",
    )
    parser.add_argument(
        "--imap-password",
        default="",
        help="IMAP app password for password-based login fallback (overrides conn string password)",
    )
    parser.add_argument(
        "conn",
        nargs="?",
        default=CONN_STRING,
        help="Credential string: email----password----client_id----refresh_token",
    )
    args = parser.parse_args()

    level: int = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve credentials: conn string takes priority, then individual flags
    email: str = args.email
    client_id: str = args.client_id
    refresh_token: str = args.refresh_token
    imap_password: str = args.imap_password

    if args.conn:
        email, password, client_id, refresh_token = _parse_conn(args.conn)
        # Use password from conn string as IMAP fallback unless overridden
        if not imap_password:
            imap_password = password

    # Validate
    if not client_id or not refresh_token or not email:
        print("❌ Missing required credentials!")
        print()
        print("   Provide a credential string:")
        print("     uv run test/email/main.py 'email----password----client_id----refresh_token'")
        print()
        print("   Or individual flags:")
        print("     uv run test/email/main.py --client-id ID --refresh-token RT --email E")
        print()
        print("   How to get a refresh_token:")
        print(
            "   1. Register an app at https://portal.azure.com/"
            "#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
        )
        print(
            "   2. Add redirect URI: https://login.microsoftonline.com/common/oauth2/nativeclient"
        )
        print("   3. API Permissions: Mail.Read + IMAP.AccessAsUser.All")
        print("   4. Visit (replace CLIENT_ID):")
        print("      https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?")
        print("        client_id=CLIENT_ID")
        print("        &response_type=code")
        print("        &redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient")
        print(
            "        &scope=https://graph.microsoft.com/Mail.Read "
            "+https://outlook.office.com/IMAP.AccessAsUser.All+offline_access"
        )
        print("        &response_mode=query")
        print("   5. Copy `code` from redirect URL, then:")
        print("      curl -X POST https://login.microsoftonline.com/consumers/oauth2/v2.0/token \\")
        print("        -d 'client_id=CLIENT_ID' \\")
        print("        -d 'grant_type=authorization_code' \\")
        print("        -d 'code=CODE_FROM_STEP_5' \\")
        print(
            "        -d 'redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient'"
        )
        sys.exit(1)

    result: FetchResult = fetch_emails(
        email_addr=email,
        client_id=client_id,
        refresh_token=refresh_token,
        folder=args.folder,
        skip=args.skip,
        top=args.top,
        use_imap=args.imap_only,
        imap_password=imap_password,
    )

    if args.json:
        output: dict[str, object] = {
            "success": result.success,
            "method": result.method,
            "has_more": result.has_more,
            "error": result.error,
            "emails": [
                {
                    "id": e.id,
                    "subject": e.subject,
                    "from": e.from_address,
                    "date": e.date,
                    "is_read": e.is_read,
                    "has_attachments": e.has_attachments,
                    "body_preview": e.body_preview,
                }
                for e in result.emails
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_result(result)


if __name__ == "__main__":
    main()
