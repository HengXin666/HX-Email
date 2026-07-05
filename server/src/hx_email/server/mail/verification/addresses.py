"""Email address helpers for verification mailbox lookup.

Rules live here so verification reads, mailbox fetch storage, and legacy
address-based extraction agree on one delivery identity model:

- Gmail ignores dots and plus tags for delivery.
- Other providers keep real aliases separate, but plus tags remain a supported
  compatibility form of the same base address.
"""

from dataclasses import dataclass
from email.utils import getaddresses

GMAIL_DOMAINS: frozenset[str] = frozenset({"gmail.com", "googlemail.com"})
GMAIL_PROVIDERS: frozenset[str] = frozenset({"gmail", "googlemail"})


@dataclass(frozen=True)
class DeliveryTarget:
    address: str
    provider: str = ""
    kind: str = "custom"


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


def normalize_provider(provider: str) -> str:
    return provider.strip().lower()


def is_gmail_provider(provider: str) -> bool:
    return normalize_provider(provider) in GMAIL_PROVIDERS


def is_gmail_address(address: str) -> bool:
    cleaned: str = email_address_value(address).lower()
    if "@" not in cleaned:
        return False
    domain: str = cleaned.rsplit("@", 1)[1]
    return domain in GMAIL_DOMAINS


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


def recipient_matches_target(target_address: str | DeliveryTarget, recipient_address: str) -> bool:
    target: DeliveryTarget = coerce_delivery_target(target_address)
    for recipient in recipient_addresses(recipient_address):
        if addresses_match_for_delivery(target, recipient):
            return True
    return False


def coerce_delivery_target(target: str | DeliveryTarget) -> DeliveryTarget:
    if isinstance(target, DeliveryTarget):
        return target
    return DeliveryTarget(address=target)


def addresses_match_for_delivery(target: str | DeliveryTarget, recipient_address: str) -> bool:
    delivery_target: DeliveryTarget = coerce_delivery_target(target)
    target_address: str = email_address_value(delivery_target.address).lower()
    recipient: str = email_address_value(recipient_address).lower()
    if target_address == recipient:
        return True
    if is_gmail_provider(delivery_target.provider) or is_gmail_address(target_address):
        return normalize_delivery_address(target_address) == normalize_delivery_address(recipient)
    return normalize_plus_subaddress(target_address) == normalize_plus_subaddress(recipient)


def message_matches_target(target: str | DeliveryTarget, recipient_address: str | None) -> bool:
    delivery_target: DeliveryTarget = coerce_delivery_target(target)
    if not recipient_address:
        return delivery_target.kind != "alias"
    return recipient_matches_target(delivery_target, recipient_address)


def recipient_addresses(value: str) -> tuple[str, ...]:
    parsed = tuple(
        address.strip().lower() for _name, address in getaddresses([value]) if "@" in address
    )
    if parsed:
        return parsed
    cleaned = value.strip().lower()
    return (cleaned,) if "@" in cleaned else ()
