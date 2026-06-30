"""Run a Graph mail fetch through the fixed local group proxy.

Usage:
    uv run test/proxy_emali/main.py -v 'email----password----client_id----refresh_token'
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from test.proxy_emali.proxy_fetcher import EmailItem, FetchResult, fetch_emails  # noqa: E402

PROXY_URL: str = "http://127.0.0.1:2334"
CONN_STRING: str = ""
FOLDER: str = "inbox"
TOP: int = 20
SKIP: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Graph requests proxy fetch debug harness")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--email", default="")
    parser.add_argument("--client-id", default="")
    parser.add_argument("--refresh-token", default="")
    parser.add_argument("--folder", default=FOLDER)
    parser.add_argument("--top", type=int, default=TOP)
    parser.add_argument("--skip", type=int, default=SKIP)
    parser.add_argument("conn", nargs="?", default=CONN_STRING)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    email_addr: str = args.email
    client_id: str = args.client_id
    refresh_token: str = args.refresh_token
    if args.conn:
        email_addr, _password, client_id, refresh_token = _parse_conn(args.conn)

    if not email_addr or not client_id or not refresh_token:
        raise SystemExit(
            "Missing credentials. Use: email----password----client_id----refresh_token"
        )

    result = fetch_emails(
        email_addr=email_addr,
        client_id=client_id,
        refresh_token=refresh_token.rstrip("$"),
        proxy_url=PROXY_URL,
        folder=args.folder,
        top=args.top,
        skip=args.skip,
    )
    if args.json:
        print(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2))
        return
    _print_result(result)


def _parse_conn(raw: str) -> tuple[str, str, str, str]:
    parts: list[str] = raw.split("----")
    if len(parts) != 4:
        raise SystemExit("Expected: email----password----client_id----refresh_token")
    return parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()


def _result_to_dict(result: FetchResult) -> dict[str, object]:
    return {
        "success": result.success,
        "method": result.method,
        "error": result.error,
        "emails": [
            {
                "id": item.id,
                "subject": item.subject,
                "from": item.from_address,
                "date": item.date,
                "is_read": item.is_read,
                "has_attachments": item.has_attachments,
                "body_preview": item.body_preview,
            }
            for item in result.emails
        ],
    }


def _print_result(result: FetchResult) -> None:
    if not result.success:
        print(f"Fetch failed via {PROXY_URL}: {result.error}")
        return
    print(f"Method: {result.method}")
    print(f"Emails: {len(result.emails)}")
    for idx, item in enumerate(result.emails, start=1):
        _print_email(idx, item)


def _print_email(idx: int, item: EmailItem) -> None:
    read_mark: str = " " if item.is_read else "*"
    attach_mark: str = " attachment" if item.has_attachments else ""
    print()
    print(f"[{idx}] {read_mark} {item.subject}{attach_mark}")
    print(f"From: {item.from_address}")
    print(f"Date: {item.date}")
    print(f"ID: {item.id}")
    if item.body_preview:
        print(f"Body: {item.body_preview}")


if __name__ == "__main__":
    main()
