"""Default platform recognition rules (seed data).

每条规则 = (规则名, 匹配字段, 匹配方式, 模式列表, 目标平台);
patterns 支持一个平台对应多个域名/关键词 (contains 可动态覆盖其子域名)。
默认发行只带常见的 AI 平台与社交平台, 用户可自行扩展并导入导出分享。
"""

from __future__ import annotations

DEFAULT_PLATFORM_RULES: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    # OpenAI 家族统一识别到 OpenAI: chatgpt.com / codex.chatgpt.com 与
    # *.openai.com 同属一家, 不再拆分 ChatGPT 独立平台
    ("OpenAI", "domain", "contains", ("openai.com", "chatgpt.com"), "OpenAI"),
    ("Anthropic", "domain", "contains", ("anthropic.com", "claude.ai"), "Anthropic"),
    ("DeepSeek", "domain", "contains", ("deepseek.com", "deepseek.cn"), "DeepSeek"),
    ("Google", "domain", "contains", ("google", "youtube.com"), "Google"),
    (
        "Microsoft",
        "domain",
        "contains",
        ("microsoft.com", "outlook.com", "hotmail.com", "live.com"),
        "Microsoft",
    ),
    ("Apple", "domain", "contains", ("apple", "icloud.com"), "Apple"),
    ("Telegram", "domain", "contains", ("telegram.org", "telegram.me"), "Telegram"),
    ("Discord", "domain", "contains", ("discord.com", "discord.gg"), "Discord"),
    ("WhatsApp", "domain", "contains", ("whatsapp.com",), "WhatsApp"),
    ("X", "domain", "exact", ("x.com", "x.ai"), "X"),
    ("Reddit", "domain", "contains", ("reddit",), "Reddit"),
    ("Steam", "domain", "contains", ("steampowered.com", "steamcommunity.com"), "Steam"),
    ("GitHub", "domain", "contains", ("github.com", "githubusercontent.com"), "GitHub"),
    ("Patreon", "domain", "contains", ("patreon.com",), "Patreon"),
    ("Netflix", "domain", "contains", ("netflix.com",), "Netflix"),
)
