from localdirectory.plugins.fhrs import _directory_category


def item(name: str, business_type: str) -> dict:
    return {"BusinessName": name, "BusinessType": business_type}


def test_fhrs_retailers_are_shops_not_food_by_default():
    assert _directory_category(item("Aldi Stores Limited", "Retailers - supermarkets/hypermarkets")) == "shops"
    assert _directory_category(item("Holland and Barrett", "Retailers - other")) == "shops"


def test_fhrs_caring_premises_are_health_care():
    assert _directory_category(item("Example Care Home", "Caring Premises")) == "health_care"


def test_fhrs_schools_get_education_category():
    assert _directory_category(item("Lewes School", "School/college/university")) == "education_childcare"


def test_fhrs_accommodation_gets_accommodation_category():
    assert _directory_category(item("Example Guest House", "Hotel/bed & breakfast/guest house")) == "accommodation"


def test_fhrs_food_producers_are_distinct_from_restaurants():
    assert _directory_category(item("Example Foods", "Manufacturers/packers")) == "food_producers"
    assert _directory_category(item("Example Farm", "Farmers/growers")) == "food_producers"


def test_fhrs_restaurants_and_caterers_remain_food_and_drink():
    assert _directory_category(item("Example Cafe", "Restaurant/Cafe/Canteen")) == "food_and_drink"
    assert _directory_category(item("Example Caterer", "Mobile caterer")) == "food_and_drink"
