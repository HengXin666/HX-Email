import argparse
from collections.abc import Sequence

from hx_email.config import Settings
from hx_email.database import migrate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hx-email")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        database_path = migrate(Settings())
        print(f"Migration complete: {database_path}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
