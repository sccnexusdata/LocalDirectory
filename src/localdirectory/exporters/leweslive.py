from __future__ import annotations

import json
from pathlib import Path

from localdirectory.models import ListingRecord, utc_now_iso


def export_leweslive(records: list[ListingRecord], output_dir: Path) -> Path:
    target = output_dir / "leweslive"
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        if not record.publish_safe:
            continue
        public = record.to_dict(public=True)
        rows.append({
            "id": public["listing_id"],
            "name": public["name"],
            "type": public["listing_type"],
            "category": public["primary_category"],
            "description": public["description"],
            "website": public["website"],
            "phone": public["phone"],
            "email": public["email"],
            "address": public["address"],
            "postcode": public["postcode"],
            "lat": public["latitude"],
            "lng": public["longitude"],
            "serviceArea": public["service_area"],
            "confidence": public["confidence_score"],
            "sources": public["sources"],
            "lastChecked": public["last_seen"],
        })
    payload = {"schemaVersion": "1.0", "generatedAt": utc_now_iso(), "listings": rows}
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    (target / "directory.v1.json").write_text(text, encoding="utf-8")
    (target / "directory.v1.js").write_text("window.LEWESLIVE_DIRECTORY = " + text + ";\n", encoding="utf-8")
    (target / "manifest.v1.json").write_text(json.dumps({"record_count": len(rows), "generated_at": payload["generatedAt"]}, indent=2), encoding="utf-8")
    return target
