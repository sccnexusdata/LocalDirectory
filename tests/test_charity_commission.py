import io
import json
import zipfile

from localdirectory.plugins.charity_commission import (
    _candidate_rows,
    _discover_charity_zip_url,
    _read_charity_rows,
    _records_from_rows,
)


def test_discover_charity_json_zip_prefers_main_charity_row():
    html = """
    <table>
      <tr><td>charity</td><td><a href="/data/publicextract.charity.zip">download json</a></td></tr>
      <tr><td>charity_annual_return_history</td><td><a href="/data/annual.zip">download json</a></td></tr>
    </table>
    """
    assert _discover_charity_zip_url(html, "https://register-of-charities.charitycommission.gov.uk/en/register/") == (
        "https://register-of-charities.charitycommission.gov.uk/data/publicextract.charity.zip"
    )


def test_read_charity_rows_from_json_zip():
    payload = [{"organisation_number": 12, "charity_name": "Lewes Good Cause"}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("publicextract.charity.json", json.dumps(payload))
    assert _read_charity_rows(buffer.getvalue()) == payload


def test_charity_candidates_require_registered_main_charity_and_prefix():
    rows = [
        {
            "organisation_number": 1,
            "registered_charity_number": 100001,
            "charity_name": "Lewes Good Cause",
            "charity_registration_status": "Registered",
            "linked_charity_number": 0,
            "charity_contact_postcode": "BN7 2AA",
        },
        {
            "organisation_number": 2,
            "registered_charity_number": 100002,
            "charity_name": "Removed Cause",
            "charity_registration_status": "Removed",
            "linked_charity_number": 0,
            "charity_contact_postcode": "BN7 2AB",
        },
        {
            "organisation_number": 3,
            "registered_charity_number": 100003,
            "charity_name": "Linked Cause",
            "charity_registration_status": "Registered",
            "linked_charity_number": 1,
            "charity_contact_postcode": "BN7 2AC",
        },
        {
            "organisation_number": 4,
            "registered_charity_number": 100004,
            "charity_name": "Far Cause",
            "charity_registration_status": "Registered",
            "linked_charity_number": 0,
            "charity_contact_postcode": "SW1A 1AA",
        },
    ]
    candidates = _candidate_rows(rows, ("BN7", "BN8"))
    assert [row["charity_name"] for row in candidates] == ["Lewes Good Cause"]


def test_charity_records_filter_radius_and_never_publish_contact_address_or_pin():
    rows = [
        {
            "organisation_number": 101,
            "registered_charity_number": 1234567,
            "charity_name": "Lewes Good Cause",
            "charity_registration_status": "Registered",
            "linked_charity_number": 0,
            "charity_contact_address1": "1 Private Contact Road",
            "charity_contact_address3": "Lewes",
            "charity_contact_postcode": "BN7 2AA",
            "charity_contact_web": "www.example.org",
            "charity_company_registration_number": "01234567",
        },
        {
            "organisation_number": 102,
            "registered_charity_number": 7654321,
            "charity_name": "Outside Cause",
            "charity_registration_status": "Registered",
            "linked_charity_number": 0,
            "charity_contact_postcode": "BN1 1AA",
        },
    ]
    records = _records_from_rows(
        rows,
        {"BN7 2AA": (50.8739, 0.0088), "BN1 1AA": (50.70, -0.40)},
        centre_latitude=50.8739,
        centre_longitude=0.0088,
        radius_km=16.0934,
    )
    assert len(records) == 1
    record = records[0]
    assert record.name == "Lewes Good Cause"
    assert record.primary_category == "community_charities"
    assert record.listing_type == "service_provider"
    assert record.website == "https://www.example.org"
    assert record.company_number == "01234567"
    assert record.address_public is False
    assert record.latitude is None
    assert record.longitude is None
    assert record.regulator_ids["charity_commission"] == "1234567"
    assert record.sources[0].source_class == "A"
    public = record.to_dict(public=True)
    assert public["address"] == ""
    assert public["postcode"] == ""
    assert public["latitude"] is None
    assert public["longitude"] is None
