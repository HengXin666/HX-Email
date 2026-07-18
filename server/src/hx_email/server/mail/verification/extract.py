"""Verification code extraction — multi-tier with HTML stripping."""

# ruff: noqa: RUF001  — FULLWIDTH COLON intentional in CJK regex patterns

import re
from html.parser import HTMLParser

# ── Public patterns ───────────────────────────────────────────────────────

CODE_PATTERN: re.Pattern[str] = re.compile(r"\b\d{4,8}\b")
LINK_PATTERN: re.Pattern[str] = re.compile(r"https?://[^\s]+")

# ── Tier-1 context regexes (keyword embedded in pattern) ──────────────────

_CTX_RE: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:verification|confirmation|security|one[-\s]?time)\s*code"
        r"\s*(?:is|:)?\s*([A-Z0-9]{4,8})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:your|the)\s*code\s*(?:is|:)?\s*([A-Z0-9]{4,8})", re.IGNORECASE),
    re.compile(r"\bcode\s*(?:is|:)?\s*([A-Z0-9]{4,8})\b", re.IGNORECASE),
    re.compile(r"\bOTP\s*(?:is|code|:)?\s*([A-Z0-9]{4,8})\b", re.IGNORECASE),
    re.compile(r"验证码[是为:：]?\s*([A-Z0-9]{4,8})"),
    re.compile(r"激活码[是为:：]?\s*([A-Z0-9]{4,8})"),
    re.compile(r"校验码[是为:：]?\s*([A-Z0-9]{4,8})"),
    re.compile(r"动态码[是为:：]?\s*([A-Z0-9]{4,8})"),
)

# ── Keywords for Tier-2 proximity search ─────────────────────────────────

_KW: tuple[str, ...] = (
    "verification code",
    "验证码",
    "security code",
    "confirmation code",
    "one-time code",
    "激活码",
    "校验码",
    "动态码",
    "验证码是",
    "your code",
    "code is",
    "短信验证码",
    "otp",
    "passcode",
    "authentication code",
    "sign-in code",
    "login code",
)

# ── False-positive filters ───────────────────────────────────────────────


def is_junk_code(code: str) -> bool:
    """All-same-digit, sequences, years (1900-2100), or HHMM time codes."""
    if len(set(code)) == 1:
        return True
    if code in {
        "012345",
        "123456",
        "234567",
        "345678",
        "456789",
        "567890",
        "987654",
        "876543",
        "765432",
        "654321",
        "543210",
    }:
        return True
    if len(code) == 4 and code.isdigit():
        n = int(code)
        if 1900 <= n <= 2100:
            return True
        if 0 <= int(code[:2]) <= 23 and 0 <= int(code[2:]) <= 59:
            return True
    return False


# ── HTML stripper ────────────────────────────────────────────────────────


class _HTMLStripper(HTMLParser):
    """Strip style/script/head/meta/link, keep visible text."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False
        self._skip_tags = {"style", "script", "head", "meta", "link"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def strip_html(html: str) -> str:
    p = _HTMLStripper()
    p.feed(html)
    return p.text()


# ── Multi-tier extraction ────────────────────────────────────────────────


def has_verification_context(content: str) -> bool:
    """Return whether visible mail content contains verification semantics."""
    if not content:
        return False
    text: str = strip_html(content) if "<" in content and ">" in content else content
    lowered: str = text.lower()
    return any(keyword.lower() in lowered for keyword in _KW)


def extract_verification_code(content: str) -> str | None:
    """Extract a verification code from mail with explicit verification context.

    Tier 1 — context regex: ``verification code is 123456``.
    Tier 2 — keyword proximity: scan ±100 chars around known keywords.

    HTML is stripped first to prevent false positives from tracking
    pixels / inline styles. Ordinary numbers without verification semantics
    are deliberately ignored.
    """
    if not content:
        return None

    text: str = strip_html(content) if "<" in content and ">" in content else content
    if not text.strip():
        return None
    if not has_verification_context(text):
        return None

    # Tier 1: context-embedded regex (most specific)
    for pat in _CTX_RE:
        m = pat.search(text)
        if m:
            c = m.group(1).upper()
            if any(ch.isdigit() for ch in c) and not is_junk_code(c):
                return c

    # Tier 2: keyword proximity ±100 chars
    tl: str = text.lower()
    for kw in _KW:
        kwl: str = kw.lower()
        pos: int = 0
        while True:
            pos = tl.find(kwl, pos)
            if pos == -1:
                break
            ctx: str = text[max(0, pos - 100) : pos + len(kw) + 100]
            for c in CODE_PATTERN.findall(ctx):
                c = c.upper()
                if any(ch.isdigit() for ch in c) and not is_junk_code(c):
                    return c  # type: ignore[no-any-return]
            pos += len(kw)

    return None


def first_match(pattern: re.Pattern[str], content: str) -> str | None:
    m = pattern.search(content)
    return m.group(0) if m else None
