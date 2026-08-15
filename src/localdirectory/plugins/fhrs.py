from __future__ import annotations

import requests

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.taxonomy import category_from_terms
from localdirectory.text import normalise_postcode


class FHRSPlugin:
    """Food Standards Agency Food Hygiene Rating Scheme spatial search."""

    name = "fhrs"
    endpoint = "https://api.ratings.food.gov.uk/Establishments"

    def __init__(self, latitude: float, longitude: float, radius_miles: float, timeout: int = 30, user_agent: str = "LocalDirectory/0.1"):
        self.latitude = latitude
        self.longitude = longitude
        self.radius_miles = radius_miles
        self.timeout = timeout
        self.user_agent = user_agent

    def harvest(self) -> HarvestResult:
        records: list[ListingRecord] = []
        page = 1
        requests_made = 0
        while True:
            response = requests.get(
                self.endpoint,
                params={
                    "longitude": self.longitude,
                    "latitude": self.latitude,
                    "maxDistanceLimit": self.radius_miles,
                    "sortOptionKey": "distance",
                    "pageNumber": page,
                    "pageSize": 500,
                },
                headers={"x-api-version": "2", "Accept": "application/json", "User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            requests_made += 1
            response.raise_for_status()
            payload = response.json()
            items = payload.get("establishments", [])
            for item in items:
                address_parts = [
                    item.get("AddressLine1"), item.get("AddressLine2"), item.get("AddressLine3"), item.get("AddressLine4")
                ]
                geocode = item.get("geocode") or {}
                fhrs_id = str(item.get("FHRSID") or "")
                record = ListingRecord(
                    name=str(item.get("BusinessName") or "").strip(),
                    listing_type="place",
                    primary_category=category_from_terms(str(item.get("BusinessType") or ""), "food"),
                    description=_description(item),
                    phone=str(item.get("Phone") or "").strip(),
                    address=", ".join(str(x).strip() for x in address_parts if x),
                    postcode=normalise_postcode(str(item.get("PostCode") or "")),
                    latitude=_to_float(geocode.get("latitude")),
                    longitude=_to_float(geocode.get("longitude")),
                    regulator_ids={"fhrs": fhrs_id} if fhrs_id else {},
                    sources=[SourceRef("Food Standards Agency FHRS", "official_register", "A", fhrs_id, f"https://ratings.food.gov.uk/business/{fhrs_id}")],
                    quality_flags=[f"fhrs_rating:{item.get('RatingValue')}"],
                )
                if record.name:
                    records.append(record)
            meta = payload.get("meta") or {}
            total_pages = int(meta.get("totalPages") or 1)
            if page >= total_pages or not items:
                break
            page += 1
            if page > 20:
                break
        return HarvestResult(self.name, records, True, f"Harvested {len(records)} FHRS establishments", requests_made)


def _description(item: dict) -> str:
    business_type = str(item.get("BusinessType") or "Food business")
    rating = str(item.get("RatingValue") or "").strip()
    return f"{business_type}. Food hygiene record published by the Food Standards Agency" + (f"; current displayed rating: {rating}." if rating else ".")


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
