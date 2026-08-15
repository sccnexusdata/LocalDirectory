from __future__ import annotations

CATEGORY_ALIASES = {
    "beauty_and_hair": {"hairdresser", "beauty", "barber", "beauty_salon", "nails"},
    "food_and_drink": {"restaurant", "cafe", "pub", "bar", "fast_food", "food", "bakery"},
    "shops": {"shop", "retail", "clothes", "convenience", "supermarket", "books", "gift"},
    "builders_general_trades": {"builder", "handyman", "construction"},
    "plumbers_heating": {"plumber", "heating", "hvac"},
    "electricians": {"electrician", "electrical"},
    "carpenters_joiners": {"carpenter", "joiner", "cabinet_maker"},
    "roofing_chimneys_guttering": {"roofer", "roofing", "chimney", "guttering"},
    "painters_decorators": {"painter", "decorator", "painting"},
    "gardeners_landscaping_trees": {"gardener", "landscaper", "tree_surgeon", "arborist"},
    "cleaning_windows_property_care": {"cleaning", "window_cleaner", "property_maintenance"},
    "garages_vehicle_services": {"car_repair", "garage", "motorcycle_repair", "tyres"},
    "business_professional": {"lawyer", "solicitor", "accountant", "estate_agent", "financial", "office"},
    "community_charities": {"community_centre", "charity", "social_centre", "club"},
    "health_care": {"clinic", "dentist", "doctors", "pharmacy", "care", "healthcare", "veterinary"},
    "public_services": {"library", "post_office", "police", "fire_station", "townhall"},
}


def category_from_terms(*values: str) -> str:
    terms = " ".join(v.casefold() for v in values if v)
    for category, aliases in CATEGORY_ALIASES.items():
        if any(alias.replace("_", " ") in terms or alias in terms for alias in aliases):
            return category
    return "other"
