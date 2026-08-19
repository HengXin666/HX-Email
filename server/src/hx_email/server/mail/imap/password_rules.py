"""Provider-specific IMAP/SMTP password rules (leaf module, no dependencies)."""


def normalize_imap_password(provider: str, password: str) -> str:
    """Normalize a password for the provider before IMAP/SMTP login.

    Gmail app passwords are 16 chars that Google displays with spaces (``abcd
    efgh ijkl mnop``), but IMAP/SMTP login requires them without spaces. Applied
    at the point of use so already-stored values (however they were entered) are
    accepted. Other providers keep the password verbatim.
    """
    if provider.strip().lower() == "gmail":
        return "".join(password.split())
    return password
