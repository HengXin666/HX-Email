"""Safety checks for notification forwarding recipients."""

from email.utils import getaddresses

from hx_email.config import Settings
from hx_email.database import connect


def _recipient_addresses(recipient: str) -> frozenset[str]:
    parsed_addresses: frozenset[str] = frozenset(
        address.strip().casefold()
        for _display_name, address in getaddresses([recipient])
        if address.strip()
    )
    if parsed_addresses:
        return parsed_addresses
    normalized_recipient: str = recipient.strip().casefold()
    return frozenset({normalized_recipient}) if normalized_recipient else frozenset()


def is_monitored_recipient(settings: Settings, user_id: int, recipient: str) -> bool:
    recipient_addresses: frozenset[str] = _recipient_addresses(recipient)
    if not recipient_addresses:
        return False
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT address FROM usable_emails WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    monitored_addresses: set[str] = {
        str(row["address"]).strip().casefold() for row in rows if row["address"]
    }
    return bool(recipient_addresses & monitored_addresses)
