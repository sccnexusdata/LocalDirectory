from __future__ import annotations

import json
from pathlib import Path

from localdirectory.exporters.core import write_csv, write_geojson, write_json
from localdirectory.models import ListingRecord, utc_now_iso


def export_public(records: list[ListingRecord], output_dir: Path, project_name: str) -> Path:
    public_records = [record for record in records if record.publish_safe]
    bundle = output_dir / "public"
    bundle.mkdir(parents=True, exist_ok=True)
    write_json(public_records, bundle / "directory.v1.json", public=True)
    write_csv(public_records, bundle / "directory.v1.csv", public=True)
    write_geojson(public_records, bundle / "directory.v1.geojson", public=True)
    manifest = {
        "schema_version": "1.0",
        "project": project_name,
        "generated_at": utc_now_iso(),
        "record_count": len(public_records),
        "disclaimer": "Listings are signposts, not recommendations. Check current status, qualifications, insurance and regulated status directly where relevant.",
    }
    (bundle / "manifest.v1.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return bundle
