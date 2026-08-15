from pathlib import Path

from localdirectory.plugins.manual_csv import ManualCSVPlugin


def test_manual_csv_loads_seed():
    result = ManualCSVPlugin(Path("data/manual/listings.csv")).harvest()
    assert result.ok
    assert len(result.records) >= 2
    assert any(record.name == "Andy & Marvin" for record in result.records)
