from __future__ import annotations

import hashlib
from difflib import SequenceMatcher

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.text import domain, normalise_name, normalise_phone, normalise_postcode


def listing_identity(record: ListingRecord) -> str:
    parts = [normalise_name(record.name), normalise_postcode(record.postcode), domain(record.website), normalise_phone(record.phone)]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def merge_records(records: list[ListingRecord]) -> list[ListingRecord]:
    merged: list[ListingRecord] = []
    for record in records:
        match = next((candidate for candidate in merged if likely_same_entity(candidate, record)), None)
        if match is None:
            record.listing_id = listing_identity(record)
            merged.append(record)
        else:
            _merge_into(match, record)
            match.listing_id = listing_identity(match)
    return merged


def likely_same_entity(a: ListingRecord, b: ListingRecord) -> bool:
    if a.company_number and b.company_number and a.company_number == b.company_number:
        return True
    a_domain, b_domain = domain(a.website), domain(b.website)
    if a_domain and b_domain and a_domain == b_domain:
        return True
    a_phone, b_phone = normalise_phone(a.phone), normalise_phone(b.phone)
    if len(a_phone) >= 9 and a_phone == b_phone:
        return True
    a_name, b_name = normalise_name(a.name), normalise_name(b.name)
    if not a_name or not b_name:
        return False
    ratio = SequenceMatcher(None, a_name, b_name).ratio()
    a_pc, b_pc = normalise_postcode(a.postcode), normalise_postcode(b.postcode)
    if a_pc and b_pc and a_pc == b_pc and ratio >= 0.72:
        return True
    return ratio >= 0.92 and (
        a.primary_category == b.primary_category
        or "other" in {a.primary_category, b.primary_category}
    )


def _merge_into(target: ListingRecord, incoming: ListingRecord) -> None:
    for field_name in ("description", "website", "phone", "email", "address", "postcode", "company_number"):
        if not getattr(target, field_name) and getattr(incoming, field_name):
            setattr(target, field_name, getattr(incoming, field_name))
    if target.latitude is None and incoming.latitude is not None:
        target.latitude = incoming.latitude
    if target.longitude is None and incoming.longitude is not None:
        target.longitude = incoming.longitude
    if target.primary_category == "other" and incoming.primary_category != "other":
        target.primary_category = incoming.primary_category
    if target.listing_type == "registered_company" and incoming.listing_type != "registered_company":
        target.listing_type = incoming.listing_type
    target.service_area = sorted(set(target.service_area + incoming.service_area))
    target.regulator_ids.update(incoming.regulator_ids)
    target.sources = _merge_sources(target.sources, incoming.sources)
    target.manual_verified = target.manual_verified or incoming.manual_verified
    target.address_public = target.address_public and incoming.address_public
    target.phone_public = target.phone_public and incoming.phone_public
    target.email_public = target.email_public and incoming.email_public
    target.quality_flags = sorted(set(target.quality_flags + incoming.quality_flags))
    target.last_seen = max(target.last_seen, incoming.last_seen)


def _merge_sources(a: list[SourceRef], b: list[SourceRef]) -> list[SourceRef]:
    result: dict[tuple[str, str, str], SourceRef] = {item.key(): item for item in a}
    for item in b:
        result.setdefault(item.key(), item)
    return list(result.values())
