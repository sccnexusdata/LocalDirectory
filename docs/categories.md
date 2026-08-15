# Lewes local directory taxonomy

## Places and public-facing establishments

- `beauty_and_hair`
- `food_and_drink`
- `food_producers`
- `shops`
- `accommodation`
- `education_childcare`
- `community_charities`
- `health_care`
- `public_services`

## Trades and service providers

- `builders_general_trades`
- `plumbers_heating`
- `electricians`
- `carpenters_joiners`
- `roofing_chimneys_guttering`
- `painters_decorators`
- `gardeners_landscaping_trees`
- `cleaning_windows_property_care`
- `garages_vehicle_services`
- `business_professional`

## Review-only fallback

- `other`

`other` remains review-only by default. Source-specific adapters should choose the most useful directory category rather than forcing a source's regulatory scope to become the public-facing category. For example, an FHRS supermarket is a `shops` listing, a school is `education_childcare`, and a care home is `health_care` even though all three appear in the food-hygiene source.
