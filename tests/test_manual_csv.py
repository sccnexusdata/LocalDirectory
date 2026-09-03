from pathlib import Path

from localdirectory.plugins.manual_csv import ManualCSVPlugin


def test_manual_csv_loads_seed():
    result = ManualCSVPlugin(Path("data/manual/listings.csv")).harvest()
    assert result.ok
    assert len(result.records) >= 2
    assert any(record.name == "Andy & Marvin" for record in result.records)


def test_discovery_only_manual_row_suppresses_publisher_copy(tmp_path):
    source = tmp_path / "publisher-leads.csv"
    source.write_text(
        "name,primary_category,description,postcode,manual_verified,source_name,source_url,source_class,usage_mode,content_policy\n"
        "Example Shop,shops,Buy our wonderful products,BN7 2AA,true,The Lewesian,https://thelewesian.co.uk/,C,discovery_only,facts_only\n",
        encoding="utf-8",
    )

    record = ManualCSVPlugin(source).harvest().records[0]

    assert record.description == ""
    assert not record.manual_verified
    assert record.sources[0].usage_mode == "discovery_only"
    assert "publisher_copy_suppressed" in record.quality_flags
