from localdirectory.models import ListingRecord, SourceRef
from localdirectory.validation import validate_records


LOCATION = {"name": "Lewes", "latitude": 50.8739, "longitude": 0.0088, "radius_km": 16.1}
POLICY = {"minimum_independent_sources": 2, "allow_class_a_single_source": True}


def test_fhrs_like_official_record_can_publish():
    record = ListingRecord(
        name="Test Cafe",
        primary_category="food_and_drink",
        postcode="BN7 2AA",
        latitude=50.8739,
        longitude=0.0088,
        sources=[SourceRef("FSA", "official_register", "A")],
    )
    summary = validate_records([record], LOCATION, POLICY)
    assert summary.publish_safe == 1
    assert record.publish_safe


def test_companies_house_only_never_publishes():
    record = ListingRecord(
        name="Example Limited",
        listing_type="registered_company",
        primary_category="business_professional",
        postcode="BN7 2AA",
        company_number="12345678",
        sources=[SourceRef("Companies House", "official_register", "A")],
        address_public=False,
    )
    validate_records([record], LOCATION, POLICY)
    assert not record.publish_safe
    assert "registered_company_requires_trading_corroboration" in record.quality_flags


def test_charity_commission_contact_postcode_alone_is_review_only():
    record = ListingRecord(
        name="Example Charity",
        listing_type="service_provider",
        primary_category="community_charities",
        postcode="BN7 2AA",
        service_area=["Lewes"],
        sources=[SourceRef("Charity Commission for England and Wales", "official_register", "A")],
        address_public=False,
    )
    validate_records([record], LOCATION, POLICY)
    assert not record.publish_safe
    assert record.status == "review"
    assert "charity_contact_locality_requires_operational_corroboration" in record.quality_flags


def test_charity_commission_record_can_publish_when_locality_is_corroborated():
    record = ListingRecord(
        name="Example Charity",
        listing_type="service_provider",
        primary_category="community_charities",
        postcode="BN7 2AA",
        website="https://example.org",
        service_area=["Lewes"],
        sources=[
            SourceRef("Charity Commission for England and Wales", "official_register", "A"),
            SourceRef("Example Charity", "organisation_owned_website", "B"),
        ],
        address_public=False,
    )
    validate_records([record], LOCATION, POLICY)
    assert record.publish_safe
