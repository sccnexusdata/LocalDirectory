import json

import yaml

from localdirectory.config import load_config
from localdirectory.models import ListingRecord
from localdirectory.runner import DirectoryRunner


def test_offline_run_builds_segregated_outputs(tmp_path, monkeypatch):
    manual = tmp_path / "listings.csv"
    manual.write_text(
        "name,listing_type,primary_category,description,website,phone,email,address,postcode,latitude,longitude,service_area,company_number,address_public,phone_public,email_public,manual_verified,source_name,source_url\n"
        "Test Cafe,place,food_and_drink,Test,,,,1 High Street,BN7 2AA,50.8739,0.0088,Lewes,,true,true,true,true,Manual,https://example.test\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "project": {"name": "Test", "slug": "test"},
            "location": {"name": "Lewes", "latitude": 50.8739, "longitude": 0.0088, "radius_km": 10},
            "outputs": {"directory": str(tmp_path / "exports")},
            "policy": {"minimum_independent_sources": 2, "allow_class_a_single_source": True},
            "sources": {"manual_csv": str(manual)},
        }),
        encoding="utf-8",
    )
    output = DirectoryRunner(load_config(config_path), offline=True).run()
    public_records = json.loads((output / "public" / "directory.v1.json").read_text(encoding="utf-8"))
    coverage = json.loads((output / "coverage-report.json").read_text(encoding="utf-8"))
    assert len(public_records) == 1
    assert coverage["metrics"]["publish_safe_records"] == 1
    assert coverage["ready"] is True
    assert (output / "leweslive" / "directory.v1.js").exists()


def test_json_ld_queue_uses_discovered_websites_and_cap(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "project": {"name": "Test", "slug": "test"},
            "location": {"name": "Lewes", "latitude": 50.8739, "longitude": 0.0088, "radius_km": 10},
            "sources": {
                "websites": ["https://configured.example/", "not-a-url"],
                "json_ld_max_websites": 3,
            },
        }),
        encoding="utf-8",
    )
    runner = DirectoryRunner(load_config(config_path))
    records = [
        ListingRecord(name="One", website="https://one.example/"),
        ListingRecord(name="Duplicate", website="https://ONE.example/"),
        ListingRecord(name="Two", website="https://two.example/path/"),
        ListingRecord(name="Bad", website="ftp://bad.example"),
    ]

    assert runner._json_ld_urls(records) == [
        "https://configured.example",
        "https://one.example",
        "https://two.example/path",
    ]
