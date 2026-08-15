from localdirectory.entity_resolution import likely_same_entity, merge_records
from localdirectory.models import ListingRecord, SourceRef


def source(name: str, source_id: str, source_class: str = "D") -> SourceRef:
    return SourceRef(name, "test", source_class, source_id=source_id)


def test_merges_same_postcode_and_name():
    a = ListingRecord(name="Pearl Carpentry Ltd", postcode="BN7 2AA", sources=[source("A", "1", "C")])
    b = ListingRecord(name="Pearl Carpentry", postcode="BN7 2AA", website="https://pearl.example", sources=[source("B", "2", "B")])
    merged = merge_records([a, b])
    assert len(merged) == 1
    assert len(merged[0].sources) == 2
    assert merged[0].website == "https://pearl.example"


def test_same_brand_domain_different_postcodes_do_not_merge():
    lewes = ListingRecord(
        name="Subway",
        postcode="BN7 2AN",
        website="https://www.subway.com/",
        latitude=50.874,
        longitude=0.010,
        sources=[source("osm", "lewes")],
    )
    brighton = ListingRecord(
        name="Subway",
        postcode="BN1 1AA",
        website="https://www.subway.com/",
        latitude=50.822,
        longitude=-0.137,
        sources=[source("osm", "brighton")],
    )
    assert not likely_same_entity(lewes, brighton)
    assert len(merge_records([lewes, brighton])) == 2


def test_same_company_number_different_branches_do_not_merge():
    lewes = ListingRecord(
        name="Tesco",
        postcode="BN7 2BY",
        company_number="00519500",
        sources=[source("fhrs", "lewes", "A")],
    )
    hove = ListingRecord(
        name="Tesco",
        postcode="BN3 3YP",
        company_number="00519500",
        sources=[source("fhrs", "hove", "A")],
    )
    assert not likely_same_entity(lewes, hove)


def test_same_name_and_near_coordinates_can_merge_without_postcode():
    a = ListingRecord(
        name="The Example Cafe",
        latitude=50.87390,
        longitude=0.00880,
        sources=[source("osm", "node-1")],
    )
    b = ListingRecord(
        name="Example Cafe",
        latitude=50.87395,
        longitude=0.00885,
        sources=[source("fhrs", "est-1", "A")],
    )
    assert likely_same_entity(a, b)


def test_listing_id_does_not_change_when_record_is_enriched():
    a = ListingRecord(name="Independent Lewes", postcode="BN7 2AA", sources=[source("osm", "node-42")])
    b = ListingRecord(
        name="Independent Lewes",
        postcode="BN7 2AA",
        website="https://independent.example",
        phone="01273 000000",
        sources=[source("owned", "page-1", "B")],
    )
    first = merge_records([a])[0].listing_id
    enriched = merge_records([a, b])[0]
    assert enriched.listing_id == first


def test_distinct_source_objects_receive_unique_ids_even_when_names_normalise_same():
    a = ListingRecord(name="Grab & Go", postcode="BN7 2AA", sources=[source("osm", "101")])
    b = ListingRecord(name="Grab and Go", postcode="BN7 2AB", sources=[source("osm", "102")])
    merged = merge_records([a, b])
    assert len(merged) == 2
    assert len({record.listing_id for record in merged}) == 2


def test_local_description_and_address_variants_are_non_blocking():
    fhrs = ListingRecord(
        name="Caffe Nero",
        postcode="BN7 1XG",
        address="61B - 62 High Street, Lewes, East Sussex",
        description="Restaurant/Cafe/Canteen. Food hygiene record.",
        latitude=50.87260,
        longitude=0.00938,
        primary_category="food_and_drink",
        sources=[SourceRef("Food Standards Agency FHRS", "official_register", "A", source_id="1952369")],
    )
    osm = ListingRecord(
        name="Caffè Nero",
        postcode="BN7 1XG",
        address="62 High Street, Lewes",
        description="Coffee shop",
        website="https://www.caffenero.com/uk/stores/lewes",
        latitude=50.87261,
        longitude=0.00939,
        primary_category="food_and_drink",
        sources=[source("OpenStreetMap", "node/352842550")],
    )
    merged = merge_records([fhrs, osm])[0]
    assert "field_variation:description" in merged.quality_flags
    assert "field_variation:address" in merged.quality_flags
    assert not any(flag.startswith("field_conflict:") for flag in merged.quality_flags)
    assert merged.website.endswith("/lewes")


def test_conflicting_phone_remains_blocking_evidence():
    a = ListingRecord(
        name="Example Business",
        postcode="BN7 2AA",
        phone="01273 111111",
        sources=[source("official", "1", "A")],
    )
    b = ListingRecord(
        name="Example Business",
        postcode="BN7 2AA",
        phone="01273 222222",
        sources=[source("owned", "2", "B")],
    )
    merged = merge_records([a, b])[0]
    assert "field_conflict:phone" in merged.quality_flags


def test_more_specific_local_source_can_refine_broad_fhrs_category():
    fhrs = ListingRecord(
        name="Example Pharmacy",
        postcode="BN7 2AA",
        primary_category="shops",
        sources=[SourceRef("Food Standards Agency FHRS", "official_register", "A", source_id="1")],
    )
    osm = ListingRecord(
        name="Example Pharmacy",
        postcode="BN7 2AA",
        primary_category="health_care",
        sources=[source("OpenStreetMap", "node/1")],
    )
    merged = merge_records([fhrs, osm])[0]
    assert merged.primary_category == "health_care"
