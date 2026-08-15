from localdirectory.coverage import build_coverage_report
from localdirectory.models import ListingRecord, SourceRef


def _record(name: str, category: str, *, website: str = "", phone: str = "", lat: float | None = None, lon: float | None = None, sources: list[SourceRef] | None = None) -> ListingRecord:
    record = ListingRecord(
        name=name,
        primary_category=category,
        website=website,
        phone=phone,
        latitude=lat,
        longitude=lon,
        postcode="BN7 2AA",
        sources=sources or [SourceRef("OpenStreetMap", "open_map", "D")],
    )
    record.publish_safe = True
    return record


def test_coverage_report_measures_depth_contacts_and_sources():
    records = [
        _record("A", "food_and_drink", website="https://a.example", lat=50.87, lon=0.01, sources=[SourceRef("FSA", "official", "A"), SourceRef("Website", "owned", "B")]),
        _record("B", "food_and_drink", phone="01273 000000", lat=50.88, lon=0.02),
        _record("C", "food_and_drink", website="https://c.example"),
        _record("D", "plumbers_heating", phone="01273 111111", lat=50.86, lon=0.00),
        _record("E", "plumbers_heating", website="https://e.example"),
    ]
    report = build_coverage_report(
        records,
        {
            "minimum_publish_safe": 5,
            "minimum_priority_categories_with_3_records": 1,
            "minimum_trade_categories_with_2_records": 1,
            "minimum_website_coverage": 0.5,
            "minimum_contact_coverage": 0.8,
            "minimum_geocoded_coverage": 0.5,
            "minimum_multi_source_coverage": 0.2,
        },
    )

    metrics = report["metrics"]
    assert metrics["publish_safe_records"] == 5
    assert metrics["category_counts"]["food_and_drink"] == 3
    assert metrics["priority_categories_with_3_records"] == 1
    assert metrics["trade_categories_with_2_records"] == 1
    assert metrics["website_coverage"] == 0.6
    assert metrics["contact_coverage"] == 1.0
    assert metrics["geocoded_coverage"] == 0.6
    assert metrics["multi_source_coverage"] == 0.2
    assert report["ready"] is True


def test_coverage_report_blocks_shallow_directory():
    record = _record("Only one", "food_and_drink")
    report = build_coverage_report(
        [record],
        {
            "minimum_publish_safe": 10,
            "minimum_priority_categories_with_3_records": 2,
            "minimum_contact_coverage": 0.5,
        },
    )

    assert report["ready"] is False
    assert report["checks"]["minimum_publish_safe"] is False
    assert report["checks"]["minimum_priority_categories_with_3_records"] is False
    assert report["checks"]["minimum_contact_coverage"] is False
