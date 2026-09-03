from __future__ import annotations

import csv
from pathlib import Path

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode


class ManualCSVPlugin:
    name = "manual_csv"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def harvest(self) -> HarvestResult:
        if not self.path.exists():
            return HarvestResult(self.name, ok=True, message=f"No manual CSV at {self.path}")
        records: list[ListingRecord] = []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not (row.get("name") or "").strip():
                    continue
                source_url = (row.get("source_url") or "").strip()
                source_name = (row.get("source_name") or "LewesLive existing directory").strip()
                usage_mode = _usage_mode(row.get("usage_mode"))
                content_policy = (row.get("content_policy") or "structured_facts").strip().casefold()
                source_class = (row.get("source_class") or "F").strip().upper()
                discovery_only = usage_mode == "discovery_only"
                record = ListingRecord(
                    name=row["name"].strip(),
                    listing_type=(row.get("listing_type") or "place").strip(),
                    primary_category=(row.get("primary_category") or "other").strip(),
                    # Publisher copy may identify a lead, but it is not imported as
                    # directory copy. A verified source can later supply structured
                    # facts from which LewesLive writes its own description.
                    description="" if discovery_only else (row.get("description") or "").strip(),
                    website=(row.get("website") or "").strip(),
                    phone=(row.get("phone") or "").strip(),
                    email=(row.get("email") or "").strip(),
                    address=(row.get("address") or "").strip(),
                    postcode=normalise_postcode(row.get("postcode") or ""),
                    latitude=_float_or_none(row.get("latitude")),
                    longitude=_float_or_none(row.get("longitude")),
                    service_area=_split(row.get("service_area") or ""),
                    company_number=(row.get("company_number") or "").strip(),
                    address_public=_bool(row.get("address_public"), True),
                    phone_public=_bool(row.get("phone_public"), True),
                    email_public=_bool(row.get("email_public"), True),
                    manual_verified=False if discovery_only else _bool(row.get("manual_verified"), False),
                    quality_flags=["publisher_copy_suppressed"] if discovery_only and (row.get("description") or "").strip() else [],
                    sources=[
                        SourceRef(
                            source_name,
                            "manual",
                            source_class,
                            source_url=source_url,
                            usage_mode=usage_mode,
                            content_policy=content_policy,
                        )
                    ],
                )
                records.append(record)
        return HarvestResult(self.name, records=records, message=f"Loaded {len(records)} manual rows")


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y"}


def _float_or_none(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def _usage_mode(value: str | None) -> str:
    normalised = (value or "verification").strip().casefold().replace("-", "_")
    return "discovery_only" if normalised in {"discovery", "discovery_only"} else "verification"
