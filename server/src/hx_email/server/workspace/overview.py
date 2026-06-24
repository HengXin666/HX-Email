from dataclasses import dataclass
from sqlite3 import Connection

from hx_email.config import Settings
from hx_email.database import connect


@dataclass(frozen=True)
class WorkbenchOverview:
    usable_email_count: int
    active_email_count: int
    account_count: int
    temp_email_count: int
    platform_count: int
    binding_count: int
    pool_available_count: int
    pool_claimed_count: int
    verification_count: int


def get_workbench_overview(settings: Settings, user_id: int) -> WorkbenchOverview:
    with connect(settings) as connection:
        usable_email_count = count_rows(connection, "usable_emails", user_id)
        active_email_count = count_rows(connection, "usable_emails", user_id, "status = 'active'")
        account_count = count_rows(connection, "email_accounts", user_id)
        temp_email_count = count_rows(connection, "temp_mailboxes", user_id)
        platform_count = count_rows(connection, "platforms", user_id)
        binding_count = count_rows(connection, "platform_bindings", user_id)
        pool_available_count = count_rows(
            connection, "mail_pool_entries", user_id, "status = 'available'"
        )
        pool_claimed_count = count_rows(
            connection, "mail_pool_entries", user_id, "status = 'claimed'"
        )
        verification_count = count_rows(connection, "verification_readings", user_id)

    return WorkbenchOverview(
        usable_email_count=usable_email_count,
        active_email_count=active_email_count,
        account_count=account_count,
        temp_email_count=temp_email_count,
        platform_count=platform_count,
        binding_count=binding_count,
        pool_available_count=pool_available_count,
        pool_claimed_count=pool_claimed_count,
        verification_count=verification_count,
    )


def count_rows(
    connection: Connection,
    table: str,
    user_id: int,
    condition: str | None = None,
) -> int:
    where = "user_id = ?"
    if condition is not None:
        where = f"{where} AND {condition}"
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {where}",
        (user_id,),
    ).fetchone()
    return int(row[0])
