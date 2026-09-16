"""Conservative normalization: no guessed character substitutions."""
from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class ValidationResult:
    raw_text: str
    normalized_text: str
    valid: bool
    rule: str | None
    version: str


def normalize(value: str) -> str:
    # Remove formatting separators only, not arbitrary OCR hallucinations.
    return re.sub(r"[\s-]", "", value.upper())


class PlateValidator:
    def __init__(self, region: str, version: str, patterns: tuple[str, ...]):
        self.region, self.version = region, version
        self.patterns = tuple(re.compile(pattern, re.ASCII) for pattern in patterns)

    def validate(self, raw_text: str) -> ValidationResult:
        text = normalize(raw_text)
        valid_chars = 3 <= len(text) <= 16 and bool(re.fullmatch(r"[A-Z0-9]+", text, re.ASCII))
        rule = next((f"{self.region}:{i}" for i, p in enumerate(self.patterns) if valid_chars and p.fullmatch(text)), None)
        return ValidationResult(raw_text, text, rule is not None, rule, self.version)
