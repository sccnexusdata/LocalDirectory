from localdirectory.plugins.json_ld import _record
from localdirectory.taxonomy import category_from_terms


def test_schema_types_map_to_directory_taxonomy():
    assert category_from_terms("HairSalon") == "beauty_and_hair"
    assert category_from_terms("Plumber") == "plumbers_heating"
    assert category_from_terms("AccountingService") == "business_professional"
    assert category_from_terms("PostOffice") == "public_services"
    assert category_from_terms("AutoRepair") == "garages_vehicle_services"
    assert category_from_terms("BedAndBreakfast") == "accommodation"


def test_specific_schema_local_business_is_accepted_as_owned_evidence():
    record = _record(
        {
            "@type": "Plumber",
            "name": "Example Plumbing",
            "url": "https://example.test/",
            "telephone": "01273 000000",
            "address": {
                "streetAddress": "1 High Street",
                "addressLocality": "Lewes",
                "postalCode": "BN7 2AA",
            },
        },
        "https://example.test/",
    )

    assert record is not None
    assert record.primary_category == "plumbers_heating"
    assert record.postcode == "BN7 2AA"
    assert record.sources[0].source_class == "B"
    assert record.sources[0].source_type == "organisation_owned_website"


def test_non_business_schema_type_is_ignored():
    assert _record({"@type": "WebSite", "name": "Example"}, "https://example.test/") is None
