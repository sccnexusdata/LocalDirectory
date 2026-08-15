from __future__ import annotations

from collections import Counter

from localdirectory.models import ListingRecord
from localdirectory.taxonomy import CATEGORY_ALIASES


PRIORITY_CATEGORIES = tuple(CATEGORY_ALIASES)
TRADE_CATEGORIES = (
    "builders_general_trades",
    "plumbers_heating",
    "electricians",
    "carpenters_joiners",
    "roofing_chimneys_guttering",
    "painters_decorators",
    "gardeners_landscaping_trees",
    "cleaning_windows_property_care",
    "garages_vehicle_services",
    "business_professional",
)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def build_coverage_report(records: list[ListingRecord], targets: dict | None = None) -> dict:
    published = [record for record in records if record.publish_safe]
    total = len(published)
    category_counts = Counter(record.primary_category for record in published)

    website_count = sum(bool(record.website) for record in published)
    phone_count = sum(bool(record.phone) for record in published)
    email_count = sum(bool(record.email) for record in published)
    contact_count = sum(bool(record.website or record.phone or record.email) for record in published)
    geocoded_count = sum(record.latitude is not None and record.longitude is not None for record in published)
    postcode_count = sum(bool(record.postcode) for record in published)
    multi_source_count = sum(len({source.source_name.casefold() for source in record.sources}) >= 2 for record in published)
    authoritative_or_owned_count = sum(
        bool({source.source_class.upper() for source in record.sources} & {"A", "B"}) for record in published
    )

    priority_with_3 = sorted(category for category in PRIORITY_CATEGORIES if category_counts.get(category, 0) >= 3)
    trade_with_2 = sorted(category for category in TRADE_CATEGORIES if category_counts.get(category, 0) >= 2)
    missing_priority = sorted(category for category in PRIORITY_CATEGORIES if category_counts.get(category, 0) == 0)

    metrics = {
        "publish_safe_records": total,
        "category_counts": dict(sorted(category_counts.items())),
        "priority_categories_total": len(PRIORITY_CATEGORIES),
        "priority_categories_with_3_records": len(priority_with_3),
        "priority_categories_meeting_depth": priority_with_3,
        "missing_priority_categories": missing_priority,
        "trade_categories_total": len(TRADE_CATEGORIES),
        "trade_categories_with_2_records": len(trade_with_2),
        "trade_categories_meeting_depth": trade_with_2,
        "website_coverage": _ratio(website_count, total),
        "phone_coverage": _ratio(phone_count, total),
        "email_coverage": _ratio(email_count, total),
        "contact_coverage": _ratio(contact_count, total),
        "geocoded_coverage": _ratio(geocoded_count, total),
        "postcode_coverage": _ratio(postcode_count, total),
        "multi_source_coverage": _ratio(multi_source_count, total),
        "authoritative_or_owned_coverage": _ratio(authoritative_or_owned_count, total),
    }

    configured = dict(targets or {})
    checks = {
        "minimum_publish_safe": total >= int(configured.get("minimum_publish_safe", 0)),
        "minimum_priority_categories_with_3_records": len(priority_with_3)
        >= int(configured.get("minimum_priority_categories_with_3_records", 0)),
        "minimum_trade_categories_with_2_records": len(trade_with_2)
        >= int(configured.get("minimum_trade_categories_with_2_records", 0)),
        "minimum_website_coverage": metrics["website_coverage"]
        >= float(configured.get("minimum_website_coverage", 0.0)),
        "minimum_contact_coverage": metrics["contact_coverage"]
        >= float(configured.get("minimum_contact_coverage", 0.0)),
        "minimum_geocoded_coverage": metrics["geocoded_coverage"]
        >= float(configured.get("minimum_geocoded_coverage", 0.0)),
        "minimum_multi_source_coverage": metrics["multi_source_coverage"]
        >= float(configured.get("minimum_multi_source_coverage", 0.0)),
    }

    return {
        "metrics": metrics,
        "targets": configured,
        "checks": checks,
        "ready": all(checks.values()),
    }
