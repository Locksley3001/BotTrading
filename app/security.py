from __future__ import annotations

import hashlib
from typing import Any


SECRET_FIELD_NAMES = {
    "token",
    "password",
    "secret",
    "service_role",
    "authorization",
    "api_key",
    "otp",
    "chat_id",
}


def mask_secret(value: str | None, keep: int = 4) -> str | None:
    if value is None:
        return None
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}...{value[-keep:]}"


def stable_hash(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for key, value in obj.items():
            lowered = key.lower()
            if any(marker in lowered for marker in SECRET_FIELD_NAMES):
                cleaned[key] = mask_secret(str(value)) if value else value
            else:
                cleaned[key] = scrub(value)
        return cleaned
    if isinstance(obj, list):
        return [scrub(item) for item in obj]
    return obj
