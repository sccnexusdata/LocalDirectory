from localdirectory.models import ListingRecord, SourceRef
from localdirectory.postcode_enrichment import enrich_missing_coordinates


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": 200,
            "result": [
                {
                    "query": "BN7 2AA",
                    "result": {"postcode": "BN7 2AA", "latitude": 50.8739, "longitude": 0.0088},
                }
            ],
        }


def test_postcode_enrichment_adds_coordinates_without_entity_corroboration(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, timeout))
        return _Response()

    monkeypatch.setattr("localdirectory.postcode_enrichment.requests.post", fake_post)
    record = ListingRecord(
        name="Test Place",
        primary_category="shops",
        postcode="bn72aa",
        sources=[SourceRef("OpenStreetMap", "open_map", "D")],
    )

    stats = enrich_missing_coordinates([record], timeout=7, user_agent="test")

    assert stats["ok"] is True
    assert stats["postcodes_requested"] == 1
    assert stats["postcodes_resolved"] == 1
    assert stats["records_enriched"] == 1
    assert stats["requests_made"] == 1
    assert record.latitude == 50.8739
    assert record.longitude == 0.0088
    assert record.field_provenance["latitude"] == ["Postcodes.io postcode centroid"]
    assert record.field_provenance["longitude"] == ["Postcodes.io postcode centroid"]
    assert len(record.sources) == 1
    assert record.sources[0].source_name == "OpenStreetMap"
    assert calls[0][1] == {"postcodes": ["BN7 2AA"]}
