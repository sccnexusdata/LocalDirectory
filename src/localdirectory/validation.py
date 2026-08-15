from __future__ import annotations

from dataclasses import dataclass

from localdirectory.geospatial import within_radius
from localdirectory.models import ListingRecord


@dataclass(slots=True)
class ValidationSummary:
    total: int
    publish_safe: int
    review_required: int
    rejected: int


def validate_records(records: list[ListingRecord], location: dict, policy: dict) -> ValidationSummary:
    centre_lat = float(location.get("latitude", 0.0))
    centre_lon = float(location.get("longitude", 0.0))
    radius_km = float(location.get("radius_km") or float(location.get("radius_miles", 10)) * 1.609344)
    location_name = str(location.get("name", "")).casefold()
    min_sources = int(policy.get("minimum_independent_sources", 2))
    allow_class_a_single = bool(policy.get("allow_class_a_single_source", True))

    rejected = 0
    for record in records:
        flags = set(record.quality_flags)
        if not record.name:
            flags.add("missing_name")
        if record.primary_category == "other":
            flags.add("uncategorised")

        is_local_place = within_radius(record.latitude, record.longitude, centre_lat, centre_lon, radius_km)
        if record.listing_type == "place" and record.latitude is not None and not is_local_place:
            flags.add("outside_radius")
        service_match = any(location_name in area.casefold() for area in record.service_area) if location_name else False
        if record.listing_type == "service_provider" and not (service_match or is_local_place or record.postcode):
            flags.add("service_area_unconfirmed")

        source_classes = {source.source_class.upper() for source in record.sources}
        source_names = {source.source_name.casefold() for source in record.sources}
        independent_sources = len(source_names)
        official = "A" in source_classes
        owned = "B" in source_classes

        if independent_sources == 1:
            flags.add("single_source_only")
            if source_classes == {"D"}:
                flags.add("needs_independent_corroboration")
        elif independent_sources < min_sources:
            flags.add("needs_independent_corroboration")

        core_ok = bool(record.name and record.primary_category != "other" and (record.postcode or is_local_place or service_match))
        if record.listing_type == "registered_company" and independent_sources == 1:
            core_ok = False
            flags.add("registered_company_requires_trading_corroboration")

        blocking_conflict = any(
            flag.startswith("field_conflict:") or flag.startswith("entity_resolution_conflict:")
            for flag in flags
        )
        if blocking_conflict:
            flags.add("identity_or_field_conflict")

        publish = bool(
            core_ok
            and not blocking_conflict
            and (
                record.manual_verified
                or (allow_class_a_single and official and record.listing_type != "registered_company")
                or (
                    independent_sources >= min_sources
                    and (official or owned or "C" in source_classes or "D" in source_classes)
                )
                or (owned and bool(record.website and (record.phone or record.address)))
            )
        )

        if "outside_radius" in flags or "missing_name" in flags:
            publish = False
            rejected += 1

        score = 0.25
        score += min(independent_sources, 3) * 0.16
        if official:
            score += 0.20
        if owned:
            score += 0.12
        if record.website:
            score += 0.05
        if record.phone:
            score += 0.04
        if record.postcode:
            score += 0.05
        if blocking_conflict:
            score = min(score, 0.49)
        record.confidence_score = round(min(score, 0.99), 2)
        record.publish_safe = publish
        record.review_required = not publish
        record.status = "published" if publish else ("rejected" if "outside_radius" in flags else "review")
        record.quality_flags = sorted(flags)

    return ValidationSummary(
        total=len(records),
        publish_safe=sum(1 for r in records if r.publish_safe),
        review_required=sum(1 for r in records if r.review_required and r.status != "rejected"),
        rejected=rejected,
    )
