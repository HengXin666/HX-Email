from dataclasses import dataclass


@dataclass(frozen=True)
class MailProvider:
    key: str
    label: str
    imap_host: str
    imap_port: int


MAIL_PROVIDERS: dict[str, MailProvider] = {
    "gmail": MailProvider("gmail", "Gmail", "imap.gmail.com", 993),
    "qq": MailProvider("qq", "QQ Mail", "imap.qq.com", 993),
    "163": MailProvider("163", "NetEase 163", "imap.163.com", 993),
    "126": MailProvider("126", "NetEase 126", "imap.126.com", 993),
    "outlook": MailProvider("outlook", "Outlook", "outlook.live.com", 993),
    "custom": MailProvider("custom", "Custom IMAP", "", 993),
}

DOMAIN_PROVIDERS: dict[str, str] = {
    "gmail.com": "gmail",
    "googlemail.com": "gmail",
    "qq.com": "qq",
    "foxmail.com": "qq",
    "163.com": "163",
    "126.com": "126",
    "outlook.com": "outlook",
    "hotmail.com": "outlook",
    "live.com": "outlook",
    "live.cn": "outlook",
}


def infer_provider(address: str) -> str:
    domain: str = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
    return DOMAIN_PROVIDERS.get(domain, "custom")


def provider_defaults(provider: str) -> MailProvider:
    return MAIL_PROVIDERS.get(provider, MAIL_PROVIDERS["custom"])
