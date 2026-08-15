from __future__ import annotations

import csv
import json
from pathlib import Path

from localdirectory.models import ListingRecord


def write_json(records: list[ListingRecord], path: Path, public: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.to_dict(public=public) for record in records]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(records: list[ListingRecord], path: Path, public: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.to_dict(public=public) for record in records]
    fields = [
        "listing_id", "name", "listing_type", "primary_category", "description", "website", "phone", "email",
        "address", "postcode", "latitude", "longitude", "service_area", "company_number", "regulator_ids",
        "first_seen", "last_seen", "status", "confidence_score", "review_required", "publish_safe", "quality_flags", "sources"
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for field in ("service_area", "quality_flags"):
                row[field] = "|".join(row.get(field) or [])
            for field in ("regulator_ids", "sources"):
                row[field] = json.dumps(row.get(field) or {}, ensure_ascii=False)
            writer.writerow(row)


def write_geojson(records: list[ListingRecord], path: Path, public: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for record in records:
        if record.latitude is None or record.longitude is None:
            continue
        data = record.to_dict(public=public)
        if public and not record.address_public:
            continue
        properties = dict(data)
        properties.pop("latitude", None)
        properties.pop("longitude", None)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [record.longitude, record.latitude]},
            "properties": properties,
        })
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False), encoding="utf-8")
