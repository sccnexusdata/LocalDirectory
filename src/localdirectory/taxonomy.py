from __future__ import annotations

CATEGORY_ALIASES = {
    "beauty_and_hair": {
        "hairdresser", "beauty", "barber", "beauty_salon", "nails", "hair_salon",
        "hairsalon", "beautysalon", "nailsalon", "dayspa", "healthandbeautybusiness",
        "tattoo_parlor", "tattoo",
    },
    "food_and_drink": {
        "restaurant", "cafe", "pub", "bar", "fast_food", "food", "bakery", "foodestablishment",
        "cafeorcoffeeshop", "fastfoodrestaurant", "barorpub", "brewery", "winery", "icecreamshop",
    },
    "food_producers": {"food_producer", "food_manufacturer", "farm_shop", "distillery"},
    "shops": {
        "shop", "retail", "clothes", "convenience", "supermarket", "books", "gift", "store",
        "shoppingcenter", "garden_centre", "department_store",
    },
    "accommodation": {
        "hotel", "guest_house", "bed_and_breakfast", "hostel", "lodgingbusiness", "bedandbreakfast",
        "motel", "campground", "camp_site", "resort", "chalet", "apartment",
    },
    "education_childcare": {
        "school", "college", "university", "nursery", "childcare", "childcare", "kindergarten",
        "preschool", "educationalorganization",
    },
    "builders_general_trades": {
        "builder", "handyman", "construction", "generalcontractor", "homeandconstructionbusiness",
        "locksmith", "movingcompany",
    },
    "plumbers_heating": {"plumber", "heating", "hvac", "hvacbusiness"},
    "electricians": {"electrician", "electrical"},
    "carpenters_joiners": {"carpenter", "joiner", "cabinet_maker"},
    "roofing_chimneys_guttering": {"roofer", "roofing", "chimney", "guttering", "roofingcontractor"},
    "painters_decorators": {"painter", "decorator", "painting", "housepainter"},
    "gardeners_landscaping_trees": {"gardener", "landscaper", "tree_surgeon", "arborist"},
    "cleaning_windows_property_care": {
        "cleaning", "window_cleaner", "property_maintenance", "drycleaningorlaundry", "laundry",
    },
    "garages_vehicle_services": {
        "car_repair", "garage", "motorcycle_repair", "tyres", "autorepair", "automotivebusiness",
        "autopartsstore", "autodealer", "autorental", "car_rental", "car_wash",
    },
    "business_professional": {
        "lawyer", "solicitor", "accountant", "estate_agent", "financial", "accountingservice",
        "legalservice", "realestateagent", "financialservice", "employment_agency", "employmentagency",
        "insurance", "travel_agent", "travelagency", "architect", "surveyor",
    },
    "community_charities": {"community_centre", "charity", "social_centre", "club"},
    "health_care": {
        "clinic", "dentist", "doctors", "pharmacy", "healthcare", "veterinary", "medicalbusiness",
        "physician", "veterinarycare", "care_home", "nursing_home", "optician", "physiotherapist",
        "fitness_centre", "healthclub",
    },
    "public_services": {
        "library", "post_office", "postoffice", "police", "fire_station", "townhall", "governmentoffice",
        "touristinformationcenter", "tourist_information", "emergencyservice",
    },
}


def category_from_terms(*values: str) -> str:
    terms = " ".join(v.casefold() for v in values if v)
    for category, aliases in CATEGORY_ALIASES.items():
        if any(alias.replace("_", " ") in terms or alias in terms for alias in aliases):
            return category
    return "other"
