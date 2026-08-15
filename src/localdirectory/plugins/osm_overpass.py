from __future__ import annotations

import requests

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.taxonomy import category_from_terms
from localdirectory.text import normalise_postcode


class OSMOverpassPlugin:
    name = "osm_overpass"

    def __init__(self, latitude: float, longitude: float, radius_km: float, endpoint: str = "https://overpass-api.de/api/interpreter", timeout: int = 45, user_agent: str = "LocalDirectory/0.1"):
        self.latitude = latitude
        self.longitude = longitude
        self.radius_m = int(radius_km * 1000)
        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent

    def harvest(self) -> HarvestResult:
        query = self._query()
        response = requests.post(
            self.endpoint,
            data={"data": query},
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        records: list[ListingRecord] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue
            lat, lon = _coords(element)
            category = category_from_terms(
                tags.get("shop", ""), tags.get("amenity", ""), tags.get("craft", ""),
                tags.get("office", ""), tags.get("healthcare", ""), tags.get("tourism", "")
            )
            if category == "other":
                continue
            address = _address(tags)
            osm_id = f"{element.get('type','')}/{element.get('id','')}"
            website = tags.get("website") or tags.get("contact:website") or ""
            phone = tags.get("phone") or tags.get("contact:phone") or ""
            email = tags.get("email") or tags.get("contact:email") or ""
            records.append(
                ListingRecord(
                    name=name,
                    listing_type="place",
                    primary_category=category,
                    description=_description(tags),
                    website=website,
                    phone=phone,
                    email=email,
                    address=address,
                    postcode=normalise_postcode(tags.get("addr:postcode", "")),
                    latitude=lat,
                    longitude=lon,
                    regulator_ids={"osm": osm_id},
                    sources=[SourceRef("OpenStreetMap", "open_map", "D", osm_id, f"https://www.openstreetmap.org/{osm_id}")],
                    review_required=True,
                )
            )
        return HarvestResult(self.name, records, True, f"Harvested {len(records)} OpenStreetMap candidates", 1)

    def _query(self) -> str:
        radius, lat, lon = self.radius_m, self.latitude, self.longitude
        filters = [
            '["shop"]',
            '["craft"]',
            '["office"]',
            '["healthcare"]',
            '["tourism"~"hotel|guest_house|hostel"]',
            '["amenity"~"restaurant|cafe|pub|bar|fast_food|pharmacy|clinic|dentist|veterinary|bank|post_office|library|community_centre|social_centre"]',
        ]
        clauses = []
        for filt in filters:
            for kind in ("node", "way", "relation"):
                clauses.append(f"{kind}{filt}(around:{radius},{lat},{lon});")
        return "[out:json][timeout:40];(" + "".join(clauses) + ");out center tags;"


def _coords(element: dict) -> tuple[float | None, float | None]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is None or lon is None:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _address(tags: dict) -> str:
    house = " ".join(x for x in [tags.get("addr:housenumber", ""), tags.get("addr:housename", "")] if x).strip()
    parts = [house, tags.get("addr:street", ""), tags.get("addr:city", ""), tags.get("addr:postcode", "")]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _description(tags: dict) -> str:
    kinds = [tags.get("shop"), tags.get("amenity"), tags.get("craft"), tags.get("office"), tags.get("healthcare"), tags.get("tourism")]
    kind = next((k for k in kinds if k), "local place").replace("_", " ")
    return f"OpenStreetMap-listed {kind}; operational details should be checked with the provider."
