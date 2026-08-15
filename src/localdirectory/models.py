from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class SourceRef:
    source_name: str
    source_type: str
    source_class: str
    source_id: str = ""
    source_url: str = ""
    retrieved_at: str = field(default_factory=utc_now_iso)

    def key(self) -> tuple[str, str, str]:
        return (self.source_name.casefold(), self.source_type.casefold(), self.source_id)


@dataclass(slots=True)
class ListingRecord:
    name: str
    listing_type: str = "place"
    primary_category: str = "other"
    description: str = ""
    website: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    postcode: str = ""
    latitude: float | None = None
    longitude: float | None = None
    service_area: list[str] = field(default_factory=list)
    company_number: str = ""
    regulator_ids: dict[str, str] = field(default_factory=dict)
    sources: list[SourceRef] = field(default_factory=list)
    first_seen: str = field(default_factory=utc_now_iso)
    last_seen: str = field(default_factory=utc_now_iso)
    status: str = "discovered"
    confidence_score: float = 0.0
    review_required: bool = True
    publish_safe: bool = False
    address_public: bool = True
    phone_public: bool = True
    email_public: bool = True
    manual_verified: bool = False
    quality_flags: list[str] = field(default_factory=list)
    field_provenance: dict[str, list[str]] = field(default_factory=dict)
    listing_id: str = ""

    def to_dict(self, public: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if public:
            data.pop("manual_verified", None)
            data.pop("field_provenance", None)
            if not self.address_public:
                data["address"] = ""
                data["postcode"] = ""
                data["latitude"] = None
                data["longitude"] = None
            if not self.phone_public:
                data["phone"] = ""
            if not self.email_public:
                data["email"] = ""
            data["sources"] = [
                {
                    "source_name": s.source_name,
                    "source_type": s.source_type,
                    "source_class": s.source_class,
                    "source_url": s.source_url,
                    "retrieved_at": s.retrieved_at,
                }
                for s in self.sources
            ]
        return data
