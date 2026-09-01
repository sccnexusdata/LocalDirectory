import json
from pathlib import Path

from scripts.validate_public_bundle import validate


def test_checked_in_offline_bundle_can_validate(tmp_path):
    # Missing files are correctly reported.
    errors = validate(Path(tmp_path))
    assert any("missing directory.v1.json" in error for error in errors)


def test_duplicate_listing_ids_fail_public_gate(tmp_path):
    records = [
        {"listing_id": "same", "name": "One", "publish_safe": True},
        {"listing_id": "same", "name": "Two", "publish_safe": True},
    ]
    (tmp_path / "directory.v1.json").write_text(json.dumps(records), encoding="utf-8")
    (tmp_path / "directory.v1.csv").write_text("listing_id,name\n", encoding="utf-8")
    (tmp_path / "directory.v1.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    (tmp_path / "manifest.v1.json").write_text('{"record_count":2}', encoding="utf-8")

    errors = validate(tmp_path)
    assert any("duplicate listing_id" in error for error in errors)


def test_discovery_only_record_fails_public_gate(tmp_path):
    records = [
        {
            "listing_id": "publisher-only",
            "name": "Example",
            "publish_safe": True,
            "sources": [{"source_name": "The Lewesian", "usage_mode": "discovery_only"}],
        }
    ]
    (tmp_path / "directory.v1.json").write_text(json.dumps(records), encoding="utf-8")
    (tmp_path / "directory.v1.csv").write_text("listing_id,name\n", encoding="utf-8")
    (tmp_path / "directory.v1.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    (tmp_path / "manifest.v1.json").write_text('{"record_count":1}', encoding="utf-8")

    errors = validate(tmp_path)
    assert any("no publication-verification source" in error for error in errors)
