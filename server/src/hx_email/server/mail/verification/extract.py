"""Conservative, multilingual verification-code extraction."""

# ruff: noqa: RUF001  -- multilingual literals are intentional

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

from hx_email.server.mail.verification.patterns import (
    BLOCK_TAGS,
    CONTEXT_PATTERN,
    GROUPED_PATTERN,
    NEGATIVE_PATTERN,
    NOISE_PATTERNS,
    PHONE_PATTERN,
    TOKEN_PATTERN,
)
from hx_email.server.mail.verification.patterns import (
    CODE_PATTERN as CODE_PATTERN,
)
from hx_email.server.mail.verification.patterns import (
    LINK_PATTERN as LINK_PATTERN,
)


@dataclass(frozen=True)
class _Candidate:
    code: str
    display: str
    start: int
    end: int
    shape: str


class _HTMLStripper(HTMLParser):
    """Keep visible text and useful block boundaries while dropping hidden content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered: str = tag.lower()
        if lowered in {"style", "script", "head"}:
            self.skip_depth += 1
        elif not self.skip_depth and lowered in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered: str = tag.lower()
        if lowered in {"style", "script", "head"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and lowered in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


class VerificationCodeExtractor:
    """Rank code-shaped tokens using semantic distance and negative evidence."""

    def __init__(self, content: str, subject: str = "") -> None:
        normalized_subject: str = self._normalize(subject)
        normalized_content: str = self._normalize(
            strip_html(content) if "<" in content and ">" in content else content
        )
        self.subject: str = normalized_subject
        self.text: str = "\n".join(
            part for part in (normalized_subject, normalized_content) if part
        )
        self.subject_end: int = len(normalized_subject)

    def extract(self) -> str | None:
        if not self.text.strip():
            return None
        cleaned: str = self._remove_noise(self.text)
        contexts: list[tuple[int, int]] = [
            match.span() for match in CONTEXT_PATTERN.finditer(cleaned)
        ]
        negatives: list[tuple[int, int]] = [
            match.span() for match in NEGATIVE_PATTERN.finditer(cleaned)
        ]
        candidates: list[_Candidate] = self._collect_candidates(cleaned)
        scored: dict[str, tuple[int, int, _Candidate]] = {}
        for index, candidate in enumerate(candidates):
            score: int = self._score(candidate, contexts, negatives)
            if score < 7:
                continue
            previous: tuple[int, int, _Candidate] | None = scored.get(candidate.code)
            ranked: tuple[int, int, _Candidate] = (score, -index, candidate)
            if previous is None or ranked > previous:
                scored[candidate.code] = ranked
        ranked_candidates: list[tuple[int, int, _Candidate]] = sorted(scored.values(), reverse=True)
        if not ranked_candidates:
            return None
        if len(ranked_candidates) > 1 and ranked_candidates[0][0] - ranked_candidates[1][0] <= 1:
            return None
        return ranked_candidates[0][2].code

    def _normalize(self, source: str) -> str:
        normalized: str = unicodedata.normalize("NFKC", source)
        parts: list[str] = []
        for character in normalized:
            if unicodedata.category(character) == "Cf":
                continue
            if character.isdecimal() and not character.isascii():
                parts.append(str(unicodedata.decimal(character)))
            else:
                parts.append(character)
        text: str = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[^\S\n]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _remove_noise(self, text: str) -> str:
        cleaned: str = text
        for pattern in NOISE_PATTERNS:
            cleaned = pattern.sub(lambda match: " " * len(match.group()), cleaned)
        for match in tuple(PHONE_PATTERN.finditer(cleaned)):
            if sum(character.isdigit() for character in match.group()) >= 9:
                cleaned = (
                    cleaned[: match.start()] + " " * len(match.group()) + cleaned[match.end() :]
                )
        return cleaned

    def _collect_candidates(self, text: str) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        occupied: list[tuple[int, int]] = []
        for match in GROUPED_PATTERN.finditer(text):
            code: str = re.sub(r"\D", "", match.group(1))
            if 4 <= len(code) <= 8 and not is_junk_code(code):
                candidates.append(_Candidate(code, match.group(1), *match.span(1), "grouped"))
                occupied.append(match.span(1))
        for match in TOKEN_PATTERN.finditer(text):
            if any(match.start(1) < end and match.end(1) > start for start, end in occupied):
                continue
            display: str = match.group(1)
            code = display.upper()
            if not any(character.isdigit() for character in code) or is_junk_code(code):
                continue
            if code.isdigit() or (4 <= len(code) <= 8):
                candidates.append(_Candidate(code, display, *match.span(1), "token"))
        return candidates

    def _distance(self, candidate: _Candidate, ranges: list[tuple[int, int]]) -> int | None:
        distances: list[int] = []
        for start, end in ranges:
            if candidate.start < end and candidate.end > start:
                return 0
            distances.append(
                start - candidate.end if candidate.end <= start else candidate.start - end
            )
        return min(distances) if distances else None

    def _score(
        self,
        candidate: _Candidate,
        contexts: list[tuple[int, int]],
        negatives: list[tuple[int, int]],
    ) -> int:
        score: int = 3 if candidate.code.isdigit() and len(candidate.code) == 6 else 2
        if len(candidate.code) in {4, 8}:
            score -= 1
        context_distance: int | None = self._distance(candidate, contexts)
        if context_distance is not None:
            score += (
                9
                if context_distance <= 4
                else 7
                if context_distance <= 20
                else 4
                if context_distance <= 60
                else 2
                if context_distance <= 120
                else 0
            )
        subject_context: bool = bool(CONTEXT_PATTERN.search(self.subject))
        in_subject: bool = bool(self.subject) and candidate.start <= self.subject_end
        if subject_context:
            score += 2
        if in_subject:
            score += 3
        line: str = self.text[
            self.text.rfind("\n", 0, candidate.start) + 1 : self.text.find("\n", candidate.end)
            if "\n" in self.text[candidate.end :]
            else len(self.text)
        ]
        if line.strip(" \t:：=-*#") == candidate.display:
            score += 2
        if self.text.strip(" \t\n:：=-*#") == candidate.display:
            score += 5
        negative_distance: int | None = self._distance(candidate, negatives)
        if negative_distance is not None:
            score -= 10 if negative_distance <= 12 else 5 if negative_distance <= 40 else 0
        return score


def is_junk_code(code: str) -> bool:
    """Reject obvious placeholders, years, compact dates, and HHMM times."""
    if code.isdigit() and len(set(code)) == 1:
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
    if code.isdigit() and len(code) == 4:
        value: int = int(code)
        if 1900 <= value <= 2100 or (int(code[:2]) <= 23 and int(code[2:]) <= 59):
            return True
    if code.isdigit() and len(code) == 8:
        year: int = int(code[:4])
        month: int = int(code[4:6])
        day: int = int(code[6:])
        if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return True
    return False


def strip_html(html: str) -> str:
    parser: _HTMLStripper = _HTMLStripper()
    parser.feed(html)
    return parser.text()


def has_verification_context(content: str) -> bool:
    if not content:
        return False
    extractor: VerificationCodeExtractor = VerificationCodeExtractor(content)
    return bool(CONTEXT_PATTERN.search(extractor.text))


def extract_verification_code(content: str, *, subject: str = "") -> str | None:
    """Return the highest-confidence 4-8 character verification code."""
    if not content and not subject:
        return None
    return VerificationCodeExtractor(content, subject).extract()


def first_match(pattern: re.Pattern[str], content: str) -> str | None:
    match: re.Match[str] | None = pattern.search(content)
    return match.group(0) if match else None
