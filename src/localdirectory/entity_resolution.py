from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from localdirectory.geospatial import haversine_km
from localdirectory.models import ListingRecord, SourceRef
from localdirectory.text import domain, normalise_name, normalise_phone, normalise_postcode


NEARBY_MATCH_KM = 0.15
HARD_LOCATION_CONFLICT_KM = 0.75


def listing_identity(record: ListingRecord) -> str:
    """Return a source-anchored identity that is not rewritten by enrichment.

    A stable upstream identifier is preferred. The spatial/name fallback is only used
    for records whose source has no durable identifier.
    """
    source_seed = ""
    if record.sources:
        source = record.sources[0]
        source_seed = "|".join(
            [
                source.source_name.casefold(),
                source.source_type.casefold(),
                source.source_id.strip(),
                source.source_url.strip().casefold(),
            ]
        )
    fallback = "|".join(
        [
            normalise_name(record.name),
            normalise_postcode(record.postcode),
            _coordinate_anchor(record),
            record.listing_type.casefold(),
            record.primary_category.casefold(),
        ]
    )
    key = source_seed if source_seed.strip("|") else fallback
    if source_seed.strip("|"):
        key = f"{key}|{normalise_name(record.name)}|{normalise_postcode(record.postcode)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def merge_records(records: list[ListingRecord]) -> list[ListingRecord]:
    merged: list[ListingRecord] = []
    seen_ids: set[str] = set()
    for record in records:
        _ensure_field_provenance(record)
        match = next((candidate for candidate in merged if likely_same_entity(candidate, record)), None)
        if match is None:
            record.listing_id = _unique_listing_id(record, seen_ids)
            seen_ids.add(record.listing_id)
            merged.append(record)
        else:
            _merge_into(match, record)
            # Deliberately retain the original source-anchored listing_id. Enrichment
            # must never rewrite a public identifier.
    return merged


def likely_same_entity(a: ListingRecord, b: ListingRecord) -> bool:
    """Conservatively decide whether two observations describe one local listing.

    Organisation/brand signals such as company number, domain or telephone are never
    sufficient by themselves to merge two physical branches. Physical-place matching
    requires compatible postcode/address/coordinate evidence.
    """
    if _same_source_object(a, b):
        return True

    a_name, b_name = normalise_name(a.name), normalise_name(b.name)
    if not a_name or not b_name:
        return False
    ratio = SequenceMatcher(None, a_name, b_name).ratio()

    if _hard_location_conflict(a, b):
        return False

    same_postcode = _same_postcode(a, b)
    near = _nearby(a, b, NEARBY_MATCH_KM)
    same_address = _same_address(a, b)

    if same_postcode and ratio >= 0.72:
        return True
    if near and ratio >= 0.80:
        return True
    if same_address and ratio >= 0.72:
        return True

    # Strong organisation/contact matches still need local establishment evidence.
    strong_org_signal = _same_company(a, b) or _same_domain(a, b) or _same_phone(a, b)
    local_evidence = same_postcode or near or same_address or _shared_service_area(a, b)
    if strong_org_signal and local_evidence and ratio >= 0.80:
        return True

    # Service providers without a public premises can be reconciled when both the
    # business identity and explicitly declared service area agree.
    return (
        a.listing_type == "service_provider"
        and b.listing_type == "service_provider"
        and strong_org_signal
        and _shared_service_area(a, b)
        and ratio >= 0.88
    )


def _merge_into(target: ListingRecord, incoming: ListingRecord) -> None:
    _ensure_field_provenance(target)
    _ensure_field_provenance(incoming)

    for field_name in ("description", "website", "phone", "email", "address", "postcode", "company_number"):
        current = getattr(target, field_name)
        new = getattr(incoming, field_name)
        if not current and new:
            setattr(target, field_name, new)
            target.field_provenance[field_name] = list(incoming.field_provenance.get(field_name, []))
        elif current and new:
            if _equivalent_field_value(field_name, current, new):
                target.field_provenance[field_name] = _merge_labels(
                    target.field_provenance.get(field_name, []),
                    incoming.field_provenance.get(field_name, []),
                )
            else:
                target.quality_flags.append(f"field_conflict:{field_name}")

    if target.latitude is None and incoming.latitude is not None:
        target.latitude = incoming.latitude
        target.longitude = incoming.longitude
        target.field_provenance["coordinates"] = list(incoming.field_provenance.get("coordinates", []))
    elif (
        target.latitude is not None
        and target.longitude is not None
        and incoming.latitude is not None
        and incoming.longitude is not None
    ):
        distance = haversine_km(target.latitude, target.longitude, incoming.latitude, incoming.longitude)
        if distance <= NEARBY_MATCH_KM:
            target.field_provenance["coordinates"] = _merge_labels(
                target.field_provenance.get("coordinates", []),
                incoming.field_provenance.get("coordinates", []),
            )
        elif distance > HARD_LOCATION_CONFLICT_KM:
            target.quality_flags.append("entity_resolution_conflict:coordinates")

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


def _same_source_object(a: ListingRecord, b: ListingRecord) -> bool:
    a_keys = {item.key() for item in a.sources if item.source_id}
    b_keys = {item.key() for item in b.sources if item.source_id}
    return bool(a_keys.intersection(b_keys))


def _same_postcode(a: ListingRecord, b: ListingRecord) -> bool:
    a_pc, b_pc = normalise_postcode(a.postcode), normalise_postcode(b.postcode)
    return bool(a_pc and b_pc and a_pc == b_pc)


def _same_address(a: ListingRecord, b: ListingRecord) -> bool:
    a_address, b_address = _normalise_address(a.address), _normalise_address(b.address)
    return bool(a_address and b_address and a_address == b_address)


def _same_company(a: ListingRecord, b: ListingRecord) -> bool:
    return bool(a.company_number and b.company_number and a.company_number == b.company_number)


def _same_domain(a: ListingRecord, b: ListingRecord) -> bool:
    a_domain, b_domain = domain(a.website), domain(b.website)
    return bool(a_domain and b_domain and a_domain == b_domain)


def _same_phone(a: ListingRecord, b: ListingRecord) -> bool:
    a_phone, b_phone = normalise_phone(a.phone), normalise_phone(b.phone)
    return bool(len(a_phone) >= 9 and a_phone == b_phone)


def _nearby(a: ListingRecord, b: ListingRecord, threshold_km: float) -> bool:
    if None in {a.latitude, a.longitude, b.latitude, b.longitude}:
        return False
    return haversine_km(a.latitude, a.longitude, b.latitude, b.longitude) <= threshold_km


def _hard_location_conflict(a: ListingRecord, b: ListingRecord) -> bool:
    a_pc, b_pc = normalise_postcode(a.postcode), normalise_postcode(b.postcode)
    if a_pc and b_pc and a_pc != b_pc:
        return True
    if None not in {a.latitude, a.longitude, b.latitude, b.longitude}:
        return haversine_km(a.latitude, a.longitude, b.latitude, b.longitude) > HARD_LOCATION_CONFLICT_KM
    return False


def _shared_service_area(a: ListingRecord, b: ListingRecord) -> bool:
    left = {item.casefold().strip() for item in a.service_area if item.strip()}
    right = {item.casefold().strip() for item in b.service_area if item.strip()}
    return bool(left.intersection(right))


def _normalise_address(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _coordinate_anchor(record: ListingRecord) -> str:
    if record.latitude is None or record.longitude is None:
        return ""
    return f"{record.latitude:.5f},{record.longitude:.5f}"


def _unique_listing_id(record: ListingRecord, seen_ids: set[str]) -> str:
    base = listing_identity(record)
    if base not in seen_ids:
        return base
    discriminator = "|".join(
        [
            base,
            normalise_name(record.name),
            normalise_postcode(record.postcode),
            _coordinate_anchor(record),
            str(len(seen_ids)),
        ]
    )
    return hashlib.sha256(discriminator.encode("utf-8")).hexdigest()[:20]


def _ensure_field_provenance(record: ListingRecord) -> None:
    labels = [_source_label(item) for item in record.sources]
    for field_name in ("description", "website", "phone", "email", "address", "postcode", "company_number"):
        if getattr(record, field_name) and field_name not in record.field_provenance:
            record.field_provenance[field_name] = list(labels)
    if record.latitude is not None and record.longitude is not None and "coordinates" not in record.field_provenance:
        record.field_provenance["coordinates"] = list(labels)


def _source_label(source: SourceRef) -> str:
    identifier = source.source_id or source.source_url
    return f"{source.source_name}:{identifier}" if identifier else source.source_name


def _merge_labels(a: list[str], b: list[str]) -> list[str]:
    return sorted(set(a + b))


def _equivalent_field_value(field_name: str, a: str, b: str) -> bool:
    if field_name == "postcode":
        return normalise_postcode(a) == normalise_postcode(b)
    if field_name == "phone":
        return normalise_phone(a) == normalise_phone(b)
    if field_name == "website":
        return domain(a) == domain(b)
    if field_name == "address":
        return _normalise_address(a) == _normalise_address(b)
    return a.casefold().strip() == b.casefold().strip()


def _merge_sources(a: list[SourceRef], b: list[SourceRef]) -> list[SourceRef]:
    result: dict[tuple[str, str, str], SourceRef] = {item.key(): item for item in a}
    for item in b:
        result.setdefault(item.key(), item)
    return list(result.values())
