"""Email address helpers for verification mailbox lookup."""

from email.utils import getaddresses

GMAIL_DOMAINS: frozenset[str] = frozenset({"gmail.com", "googlemail.com"})


def normalize_plus_subaddress(address: str) -> str:
    cleaned: str = email_address_value(address).lower()
    if "@" not in cleaned:
        return cleaned
    local: str
    domain: str
    local, domain = cleaned.rsplit("@", 1)
    if "+" in local:
        local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def normalize_delivery_address(address: str) -> str:
    cleaned: str = normalize_plus_subaddress(address)
    if "@" not in cleaned:
        return cleaned
    local: str
    domain: str
    local, domain = cleaned.rsplit("@", 1)
    if domain in GMAIL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def email_address_value(value: str) -> str:
    parsed = tuple(address.strip() for _name, address in getaddresses([value]) if "@" in address)
    if parsed:
        return parsed[0]
    return value.strip()


def is_delivery_alias(address: str) -> bool:
    cleaned: str = email_address_value(address).lower()
    return "@" in cleaned and normalize_delivery_address(cleaned) != cleaned


def is_plus_subaddress(address: str) -> bool:
    cleaned: str = email_address_value(address)
    if "@" not in cleaned:
        return False
    local: str = cleaned.rsplit("@", 1)[0]
    return "+" in local


def recipient_matches_target(target_address: str, recipient_address: str) -> bool:
    target: str = normalize_delivery_address(target_address)
    for recipient in recipient_addresses(recipient_address):
        if target == normalize_delivery_address(recipient):
            return True
    return False


def recipient_addresses(value: str) -> tuple[str, ...]:
    parsed = tuple(
        address.strip().lower() for _name, address in getaddresses([value]) if "@" in address
    )
    if parsed:
        return parsed
    cleaned = value.strip().lower()
    return (cleaned,) if "@" in cleaned else ()
