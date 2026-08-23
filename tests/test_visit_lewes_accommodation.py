from localdirectory.plugins.visit_lewes_accommodation import (
    _detail_urls,
    _external_website,
    _parse_detail,
    _provider_supports_accommodation,
)
from bs4 import BeautifulSoup


def test_detail_urls_accept_property_pages_but_not_category_pages():
    html = """
    <a href="/accommodation/bed-and-breakfasts">B&Bs</a>
    <a href="/accommodation/no11-p1098661">no11</a>
    <a href="/accommodation/the-grain-store-lewes">The Grain Store</a>
    <a href="/food-and-drink/the-swan">The Swan</a>
    """
    assert _detail_urls(html, "https://www.visitlewes.co.uk/accommodation/bed-and-breakfasts") == [
        "https://www.visitlewes.co.uk/accommodation/no11-p1098661",
        "https://www.visitlewes.co.uk/accommodation/the-grain-store-lewes",
    ]


def test_explicit_accommodation_page_is_categorised_without_name_inference():
    html = """
    <html><body>
      <h1>no11</h1>
      <p>Type: Guest Accommodation</p>
      <p>Mount Harry Road, LEWES, East Sussex, BN7 1NT</p>
      <p>Self Contained Annexe available per room per night.</p>
      <a href="https://no11.example/">Website</a>
    </body></html>
    """
    record = _parse_detail(html, "https://www.visitlewes.co.uk/accommodation/no11-p1098661")
    assert record is not None
    assert record.name == "no11"
    assert record.primary_category == "accommodation"
    assert record.postcode == "BN7 1NT"
    assert record.sources[0].source_class == "C"
    assert "accommodation_provider_not_yet_corroborated" in record.quality_flags


def test_pub_or_inn_name_without_room_evidence_is_not_accommodation():
    html = """
    <html><body>
      <h1>The Swan Inn</h1>
      <p>30A Southover High Street, Lewes, East Sussex, BN7 1HU</p>
      <p>A pub with bars, drinks and functions.</p>
    </body></html>
    """
    assert _parse_detail(html, "https://www.visitlewes.co.uk/accommodation/the-swan-inn") is None


def test_provider_site_requires_identity_and_explicit_stay_language():
    white_hart = """
    <html><body><h1>The White Hart, Lewes</h1>
    <p>Book a room at The White Hart. We have 23 individually styled bedrooms.</p>
    </body></html>
    """
    restaurant_only = """
    <html><body><h1>The White Hart</h1><p>Seasonal menus, Sunday lunch and cocktails.</p></body></html>
    """
    unrelated_hotel = """
    <html><body><h1>Other Place</h1><p>Hotel rooms and bedrooms available.</p></body></html>
    """
    assert _provider_supports_accommodation("The White Hart", white_hart) is True
    assert _provider_supports_accommodation("The White Hart", restaurant_only) is False
    assert _provider_supports_accommodation("The White Hart", unrelated_hotel) is False


def test_booking_and_social_links_are_not_treated_as_owned_websites():
    html = """
    <a href="https://booking.com/example">Website</a>
    <a href="https://instagram.com/example">Instagram</a>
    <a href="https://provider.example/">Visit website</a>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert _external_website(soup, "https://www.visitlewes.co.uk/accommodation/example") == (
        "https://provider.example/"
    )
