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
            "outputs": {
                "directory": str(tmp_path / "exports"),
                "site_bundle": {"slug": "leweslive", "js_global": "LEWESLIVE_DIRECTORY"},
            },
            "policy": {"minimum_independent_sources": 2, "allow_class_a_single_source": True},
            "sources": {"manual_csv": str(manual)},
        }),
        encoding="utf-8",
    )
    output = DirectoryRunner(load_config(config_path), offline=True).run()
    public_records = json.loads((output / "public" / "directory.v1.json").read_text(encoding="utf-8"))
    coverage = json.loads((output / "coverage-report.json").read_text(encoding="utf-8"))
    site_payload = json.loads((output / "leweslive" / "directory.v1.json").read_text(encoding="utf-8"))
    assert len(public_records) == 1
    assert coverage["metrics"]["publish_safe_records"] == 1
    assert coverage["ready"] is True
    assert site_payload["site"] == "leweslive"
    assert (output / "leweslive" / "directory.v1.js").read_text(encoding="utf-8").startswith(
        "window.LEWESLIVE_DIRECTORY = "
    )


def test_site_bundle_is_locality_configurable_without_lewes_leakage(tmp_path):
    manual = tmp_path / "listings.csv"
    manual.write_text(
        "name,listing_type,primary_category,description,website,phone,email,address,postcode,latitude,longitude,service_area,company_number,address_public,phone_public,email_public,manual_verified,source_name,source_url\n"
        "Brighton Test Cafe,place,food_and_drink,Test,,,,1 Test Street,BN1 1AA,50.8225,-0.1372,Brighton,,true,true,true,true,Manual,https://example.test\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "brighton.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "project": {"name": "BrightonLive Directory", "slug": "brighton"},
            "location": {"name": "Brighton", "latitude": 50.8225, "longitude": -0.1372, "radius_km": 10},
            "outputs": {
                "directory": str(tmp_path / "exports"),
                "site_bundle": {"slug": "brightonlive", "js_global": "BRIGHTONLIVE_DIRECTORY"},
            },
            "policy": {"minimum_independent_sources": 2, "allow_class_a_single_source": True},
            "sources": {"manual_csv": str(manual)},
        }),
        encoding="utf-8",
    )

    output = DirectoryRunner(load_config(config_path), offline=True).run()
    js = (output / "brightonlive" / "directory.v1.js").read_text(encoding="utf-8")
    payload = json.loads((output / "brightonlive" / "directory.v1.json").read_text(encoding="utf-8"))

    assert js.startswith("window.BRIGHTONLIVE_DIRECTORY = ")
    assert payload["site"] == "brightonlive"
    assert not (output / "leweslive").exists()
    assert "LEWESLIVE_DIRECTORY" not in js


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


def test_json_ld_queue_prioritises_trade_websites_before_food(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "project": {"name": "Test", "slug": "test"},
            "location": {"name": "Lewes", "latitude": 50.8739, "longitude": 0.0088, "radius_km": 10},
            "sources": {
                "json_ld_max_websites": 4,
                "json_ld_trade_per_category": 2,
            },
        }),
        encoding="utf-8",
    )
    runner = DirectoryRunner(load_config(config_path))
    records = [
        ListingRecord(name="Food A", primary_category="food_and_drink", website="https://food-a.example"),
        ListingRecord(name="Food B", primary_category="food_and_drink", website="https://food-b.example"),
        ListingRecord(name="Builder A", primary_category="builders_general_trades", website="https://builder-a.example"),
        ListingRecord(name="Builder B", primary_category="builders_general_trades", website="https://builder-b.example"),
        ListingRecord(name="Garage A", primary_category="garages_vehicle_services", website="https://garage-a.example"),
    ]

    urls = runner._json_ld_urls(records)
    assert urls[:2] == ["https://builder-a.example", "https://builder-b.example"]
    assert "https://garage-a.example" in urls
    assert len(urls) == 4


def test_runner_wires_opt_in_lewes_chamber_source(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "project": {"name": "Test", "slug": "test"},
            "location": {
                "name": "Lewes",
                "latitude": 50.8739,
                "longitude": 0.0088,
                "radius_km": 16.0934,
            },
            "sources": {
                "enabled": ["lewes_chamber"],
                "lewes_chamber_index_url": "https://directory.example/members/",
                "lewes_chamber_max_results": 75,
                "lewes_chamber_workers": 3,
                "lewes_chamber_timeout_seconds": 9,
            },
        }),
        encoding="utf-8",
    )

    plugins = DirectoryRunner(load_config(config_path))._plugins()
    chamber = next(plugin for plugin in plugins if plugin.name == "lewes_chamber")

    assert chamber.index_url == "https://directory.example/members/"
    assert chamber.max_results == 75
    assert chamber.max_workers == 3
    assert chamber.timeout == 9


def test_runner_wires_radius_filtered_charity_commission_source(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "project": {"name": "Test", "slug": "test"},
            "location": {
                "name": "Lewes",
                "postcode_area": "BN7",
                "latitude": 50.8739,
                "longitude": 0.0088,
                "radius_km": 16.0934,
            },
            "sources": {
                "enabled": ["charity_commission"],
                "charity_commission_candidate_postcode_prefixes": ["BN7", "BN8", "TN22"],
                "charity_commission_zip_url": "https://data.example/charity.zip",
                "charity_commission_postcode_endpoint": "https://postcodes.example/postcodes",
                "charity_commission_timeout_seconds": 70,
            },
        }),
        encoding="utf-8",
    )

    plugins = DirectoryRunner(load_config(config_path))._plugins()
    charity = next(plugin for plugin in plugins if plugin.name == "charity_commission")

    assert charity.radius_km == 16.0934
    assert charity.candidate_postcode_prefixes == ("BN7", "BN8", "TN22")
    assert charity.zip_url == "https://data.example/charity.zip"
    assert charity.postcode_endpoint == "https://postcodes.example/postcodes"
    assert charity.timeout == 70
