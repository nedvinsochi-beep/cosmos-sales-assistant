import hashlib
import re
from typing import Any

SENSITIVE_KEYS = {
    "name",
    "last_name",
    "second_name",
    "phone",
    "email",
    "comments",
    "comment",
    "description",
    "address",
    "web",
    "im",
}
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s()\-]*){7,15}(?!\w)")


def pseudonym(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"anon_{digest}"


def redact_text(value: str) -> str:
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    return PHONE_RE.sub("[REDACTED_PHONE]", value)


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in record.items():
        normalized = key.lower()
        if normalized in SENSITIVE_KEYS or normalized.startswith(("uf_crm_", "contact_")):
            clean[key] = "[REDACTED]"
        elif isinstance(value, str):
            clean[key] = redact_text(value)
        elif isinstance(value, dict):
            clean[key] = redact_record(value)
        elif isinstance(value, list):
            clean[key] = [
                redact_record(item) if isinstance(item, dict) else redact_text(item)
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            clean[key] = value
    return clean
