"""Regression tests for multilingual verification-code extraction."""

# ruff: noqa: RUF001  -- full-width characters exercise Unicode normalization

import pytest
from hx_email.server.mail.temp_mail import TempMailCode, TempMailMessage, extract_codes
from hx_email.server.mail.verification import (
    extract_verification_code,
    has_verification_context,
)


@pytest.mark.parametrize(
    ("content", "subject", "expected"),
    [
        ("セキュリティ コード: 327333", "", "327333"),
        ("", "セキュリティ コード: 327333", "327333"),
        ("رمز التحقق: ٣٢٧٣٣٣", "", "327333"),
        ("Su código de verificación es 327333.", "", "327333"),
        ("Ihr Bestätigungscode lautet 327333.", "", "327333"),
        ("Your verification code is A7B9C2.", "", "A7B9C2"),
        ("Your verification code is 129-458.", "", "129458"),
    ],
)
def test_extracts_contextual_codes_across_languages_and_shapes(
    content: str, subject: str, expected: str
) -> None:
    assert extract_verification_code(content, subject=subject) == expected


def test_normalizes_full_width_digits_and_removes_zero_width_characters() -> None:
    content = (
        "<html><head><style>.code{width:327333px}</style></head>"
        "<body><p>セキュリティ　コード：</p><strong>３２７\u200b３３３</strong></body></html>"
    )

    assert extract_verification_code(content) == "327333"


def test_prefers_semantically_closest_candidate_over_reference_number() -> None:
    content = (
        "Reference ID 871623 is for support only. "
        "Your verification code is 327333 and expires in ten minutes."
    )

    assert extract_verification_code(content) == "327333"


@pytest.mark.parametrize(
    ("content", "subject"),
    [
        ("Order 327333 was shipped today.", "Order update"),
        ("Order number 327333 was shipped today.", "Your verification code"),
        ("The appointment is 2026-08-09 at 13:52.", "Your verification code"),
        ("Call support at +1 (800) 555-0199.", "Security code assistance"),
        ("Open https://example.test/verify/327333 to continue.", "Verification link"),
        ("Card security code: 4829", "Payment confirmation"),
        ("<style>.code{width:327333px}</style><p>Welcome to our newsletter.</p>", "Welcome"),
    ],
)
def test_rejects_common_non_otp_numbers(content: str, subject: str) -> None:
    assert extract_verification_code(content, subject=subject) is None


def test_abstains_when_two_contextual_candidates_are_equally_likely() -> None:
    content = "Verification code: 327333 or verification code: 719284"

    assert extract_verification_code(content) is None


def test_temp_mail_extraction_uses_subject_and_preserves_message_metadata() -> None:
    messages = (
        TempMailMessage(
            id="microsoft-ja",
            from_address="account-security-noreply@accountprotection.microsoft.com",
            subject="セキュリティ コード: 327333",
            text="Microsoft アカウントの本人確認に使用してください。",
            received_at="2026-08-09T13:52:00+08:00",
        ),
    )

    assert extract_codes(messages) == (
        TempMailCode(
            message_id="microsoft-ja",
            code="327333",
            received_at="2026-08-09T13:52:00+08:00",
        ),
    )


def test_detects_multilingual_verification_context() -> None:
    assert has_verification_context("セキュリティ コード: 327333") is True
    assert has_verification_context("Order 327333 was shipped") is False
