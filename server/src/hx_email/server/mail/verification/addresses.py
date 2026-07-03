"""Email address helpers for verification mailbox lookup."""


def normalize_plus_subaddress(address: str) -> str:
    cleaned: str = address.strip()
    if "@" not in cleaned:
        return cleaned
    local: str
    domain: str
    local, domain = cleaned.rsplit("@", 1)
    if "+" in local:
        local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def is_plus_subaddress(address: str) -> bool:
    cleaned: str = address.strip()
    if "@" not in cleaned:
        return False
    local: str = cleaned.rsplit("@", 1)[0]
    return "+" in local


def recipient_matches_target(target_address: str, recipient_address: str) -> bool:
    target: str = target_address.strip().lower()
    recipient: str = recipient_address.strip().lower()
    if target == recipient:
        return True
    return normalize_plus_subaddress(target).lower() == normalize_plus_subaddress(recipient).lower()
