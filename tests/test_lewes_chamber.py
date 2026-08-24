from localdirectory.plugins.lewes_chamber import (
    _index_candidates,
    _member_urls,
    _parse_member,
    _record_from_index_candidate,
)


def test_member_urls_accept_current_directory_detail_pages():
    html = """
    <a href="/members-directory/">Directory</a>
    <a href="/members-directory/value-home-supplies/">Value Home Supplies</a>
    <a href="/members-directory/astburys-solicitors/">Astburys Solicitors</a>
    """
    assert _member_urls(html, "https://www.leweschamber.co.uk/members-directory/") == [
        "https://www.leweschamber.co.uk/members-directory/astburys-solicitors/",
        "https://www.leweschamber.co.uk/members-directory/value-home-supplies/",
    ]


def test_parse_current_chamber_member_structure_without_phone_email_ingest():
    html = """
    <html><head><title>Astburys Solicitors - Member of Lewes Chamber of Commerce</title></head><body>
      <main>
        <h1>Astburys Solicitors</h1>
        <ul>
          <li>Address:</li><li>Lewes House, 39 High Street</li><li>Lewes</li><li>East Sussex</li><li>BN7 2LU</li><li>United Kingdom</li>
          <li>Sector:</li><li>Solicitors</li>
        </ul>
        <p>01273 405900</p><p>jastbury@astburys-law.co.uk</p>
        <a href="https://www.astburys-law.co.uk/">Website</a>
        <p>Astburys Solicitors is a small approachable general legal practice specialising in property and private client work.</p>
      </main>
    </body></html>
    """
    record = _parse_member(html, "https://www.leweschamber.co.uk/members-directory/astburys-solicitors/")
    assert record is not None
    assert record.name == "Astburys Solicitors"
    assert record.postcode == "BN7 2LU"
    assert record.primary_category == "business_professional"
    assert record.website == "https://www.astburys-law.co.uk"
    assert record.phone == ""
    assert record.email == ""
    assert record.sources[0].source_class == "C"


def test_member_without_address_remains_service_provider():
    html = """
    <html><head><title>Create Time - Member of Lewes Chamber of Commerce</title></head><body>
      <main><h1>Create Time</h1><p>Sector:</p><p>Business Support</p>
      <a href="https://create-time.co.uk/">Website</a>
      <p>A virtual assistant supporting local businesses with administration and workflow organisation.</p></main>
    </body></html>
    """
    record = _parse_member(html, "https://www.leweschamber.co.uk/members-directory/create-time/")
    assert record is not None
    assert record.listing_type == "service_provider"
    assert record.service_area == ["Lewes"]


def test_index_candidate_preserves_visible_name_without_inventing_detail_fields():
    html = """
    <div class="member-card category-garden-services">
      <a href="/members-directory/arcadia-garden-design/">Arcadia Garden Design</a>
    </div>
    """
    candidates = _index_candidates(html, "https://www.leweschamber.co.uk/members-directory/")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.name == "Arcadia Garden Design"
    record = _record_from_index_candidate(candidate)
    assert record.name == "Arcadia Garden Design"
    assert record.website == ""
    assert record.address == ""
    assert record.phone == ""
    assert record.email == ""
    assert record.listing_type == "service_provider"
    assert record.review_required is True
    assert "chamber_index_only_requires_owned_or_independent_corroboration" in record.quality_flags
