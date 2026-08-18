from __future__ import annotations

import json
import re
from pathlib import Path

from localdirectory.models import ListingRecord, utc_now_iso

_SITE_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_JS_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def export_site_bundle(
    records: list[ListingRecord],
    output_dir: Path,
    *,
    site_slug: str,
    js_global: str,
) -> Path:
    """Write the governed browser bundle for one configured presentation site.

    The directory engine owns the data contract; the consuming website owns its
    branding and presentation.  A locality therefore selects only a safe output
    slug and JavaScript namespace here instead of requiring a site-specific
    exporter implementation.
    """
    slug = str(site_slug or "").strip().lower()
    global_name = str(js_global or "").strip()
    if not _SITE_SLUG.fullmatch(slug):
        raise ValueError(f"Invalid site bundle slug: {site_slug!r}")
    if not _JS_IDENTIFIER.fullmatch(global_name):
        raise ValueError(f"Invalid site bundle JavaScript global: {js_global!r}")

    target = output_dir / slug
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

    payload = {
        "schemaVersion": "1.0",
        "generatedAt": utc_now_iso(),
        "site": slug,
        "listings": rows,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    (target / "directory.v1.json").write_text(text, encoding="utf-8")
    (target / "directory.v1.js").write_text(
        f"window.{global_name} = " + text + ";\n",
        encoding="utf-8",
    )
    (target / "manifest.v1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "site": slug,
                "js_global": global_name,
                "record_count": len(rows),
                "generated_at": payload["generatedAt"],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return target
