"""Patterns and semantic labels used by verification-code extraction."""

# ruff: noqa: RUF001  -- multilingual literals are intentional

import re

CODE_PATTERN: re.Pattern[str] = re.compile(r"\b\d{4,8}\b")
LINK_PATTERN: re.Pattern[str] = re.compile(r"https?://[^\s]+")

CONTEXT_TERMS: tuple[str, ...] = (
    "otp",
    "totp",
    "verification code",
    "verification number",
    "security code",
    "confirmation code",
    "authentication code",
    "authorization code",
    "one-time code",
    "one time code",
    "one-time password",
    "one time password",
    "one-time passcode",
    "passcode",
    "sign-in code",
    "sign in code",
    "login code",
    "access code",
    "activation code",
    "your code is",
    "your code:",
    "验证码",
    "驗證碼",
    "验证代码",
    "驗證代碼",
    "安全代码",
    "安全碼",
    "确认码",
    "確認碼",
    "一次性代码",
    "一次性密碼",
    "动态密码",
    "動態密碼",
    "セキュリティコード",
    "セキュリティ コード",
    "認証コード",
    "確認コード",
    "認証番号",
    "ワンタイムコード",
    "ワンタイムパスワード",
    "인증 코드",
    "인증코드",
    "인증번호",
    "확인 코드",
    "일회용 비밀번호",
    "código de verificación",
    "codigo de verificacion",
    "código de segurança",
    "codigo de seguranca",
    "code de vérification",
    "code de verification",
    "code de sécurité",
    "bestätigungscode",
    "bestaetigungscode",
    "verifizierungscode",
    "sicherheitscode",
    "codice di verifica",
    "codice di sicurezza",
    "verificatiecode",
    "beveiligingscode",
    "kod weryfikacyjny",
    "kod bezpieczeństwa",
    "код подтверждения",
    "проверочный код",
    "одноразовый код",
    "одноразовый пароль",
    "رمز التحقق",
    "كود التحقق",
    "رمز التأكيد",
    "رمز الأمان",
    "كلمة المرور لمرة واحدة",
    "doğrulama kodu",
    "guvenlik kodu",
    "güvenlik kodu",
    "tek kullanımlık kod",
)
CONTEXT_PATTERN: re.Pattern[str] = re.compile(
    "|".join(re.escape(term) for term in sorted(CONTEXT_TERMS, key=len, reverse=True)),
    re.IGNORECASE,
)
NEGATIVE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:order|invoice|tracking|reference|ticket|customer|account|phone|mobile|"
    r"date|time|price|amount|total|postal|zip|sku|card|cvv|cvc)\b|"
    r"(?:订单|訂單|发票|發票|运单|運單|参考|參考|日期|时间|時間|电话|電話|卡号|卡號)|"
    r"(?:注文|請求書|追跡|参照|日付|時刻|電話|カード)",
    re.IGNORECASE,
)
TOKEN_PATTERN: re.Pattern[str] = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{4,10})(?![A-Za-z0-9])")
GROUPED_PATTERN: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,4}(?:[ -]\d{1,4}){1,5})(?![A-Za-z0-9])"
)
NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE),
    re.compile(r"[\w.+-]+@[\w.-]+\.\w+"),
    re.compile(r"(?<!\d)\d{9,}(?!\d)"),
    re.compile(
        r"(?<!\d)(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])" r"[-/.](?:0?[1-9]|[12]\d|3[01])(?!\d)"
    ),
    re.compile(
        r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])"
        r"[-/.](?:\d{2}|(?:19|20)\d{2})(?!\d)"
    ),
    re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?!\d)"),
    re.compile(r"[$€£¥￥]\s*\d[\d,.]*"),
)
PHONE_PATTERN: re.Pattern[str] = re.compile(r"\+?\d[\d\s().-]{7,}\d")
BLOCK_TAGS: frozenset[str] = frozenset(
    {"br", "div", "p", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}
)
