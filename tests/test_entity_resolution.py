from localdirectory.entity_resolution import merge_records
from localdirectory.models import ListingRecord, SourceRef


def test_merges_same_postcode_and_name():
    a = ListingRecord(name="Pearl Carpentry Ltd", postcode="BN7 2AA", sources=[SourceRef("A", "x", "C")])
    b = ListingRecord(name="Pearl Carpentry", postcode="BN7 2AA", website="https://pearl.example", sources=[SourceRef("B", "y", "B")])
    merged = merge_records([a, b])
    assert len(merged) == 1
    assert len(merged[0].sources) == 2
    assert merged[0].website == "https://pearl.example"
