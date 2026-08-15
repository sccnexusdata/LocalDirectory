from __future__ import annotations

import re
from urllib.parse import urlparse


def normalise_name(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"\b(limited|ltd|plc|llp)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalise_postcode(value: str) -> str:
    compact = re.sub(r"\s+", "", value or "").upper()
    if len(compact) > 3:
        return f"{compact[:-3]} {compact[-3:]}"
    return compact


def normalise_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("44"):
        digits = "0" + digits[2:]
    return digits


def domain(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc.casefold().split(":", 1)[0]
    return host.removeprefix("www.")
