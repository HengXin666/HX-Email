import argparse
import json
from collections.abc import Sequence

from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.sync.service import SyncReport, push_snapshot, run_sync


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hx-email")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")
    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument(
        "--push-only", action="store_true", help="只推送本地快照到主节点, 不拉取"
    )

    args = parser.parse_args(argv)
    if args.command == "migrate":
        database_path = migrate(Settings())
        print(f"Migration complete: {database_path}")
        return 0
    if args.command == "sync":
        report: SyncReport = push_snapshot(Settings()) if args.push_only else run_sync(Settings())
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 1 if report.error else 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
