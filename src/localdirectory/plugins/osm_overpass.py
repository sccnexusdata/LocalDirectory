from __future__ import annotations

import time

import requests

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.taxonomy import category_from_terms
from localdirectory.text import normalise_postcode


DEFAULT_OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)


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
        payload, endpoint, attempts = self._request_payload(query)
        records: list[ListingRecord] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue
            lat, lon = _coords(element)
            category = category_from_terms(
                tags.get("shop", ""), tags.get("amenity", ""), tags.get("craft", ""),
                tags.get("office", ""), tags.get("healthcare", ""), tags.get("tourism", ""),
                tags.get("leisure", "")
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
        message = f"Harvested {len(records)} OpenStreetMap candidates via {endpoint}"
        if attempts > 1:
            message += f" after {attempts} endpoint attempts"
        return HarvestResult(self.name, records, True, message, attempts)

    def _request_payload(self, query: str) -> tuple[dict, str, int]:
        endpoints = _ordered_endpoints(self.endpoint)
        failures: list[str] = []
        attempts = 0
        for endpoint_index, endpoint in enumerate(endpoints):
            # One retry per endpoint handles short-lived 429/5xx/load-shedding events.
            for retry in range(2):
                attempts += 1
                try:
                    response = requests.post(
                        endpoint,
                        data={"data": query},
                        headers={
                            "Accept": "application/json",
                            "Accept-Encoding": "gzip, deflate",
                            "User-Agent": self.user_agent,
                        },
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or "elements" not in payload:
                        raise ValueError("Overpass response did not contain an elements array")
                    return payload, endpoint, attempts
                except (requests.RequestException, ValueError) as exc:
                    failures.append(f"{endpoint}: {type(exc).__name__}: {exc}")
                    if retry == 0:
                        time.sleep(1)
            if endpoint_index < len(endpoints) - 1:
                time.sleep(1)
        raise RuntimeError("All Overpass endpoints failed: " + " | ".join(failures))

    def _query(self) -> str:
        radius, lat, lon = self.radius_m, self.latitude, self.longitude
        filters = [
            '["shop"]',
            '["craft"]',
            '["office"]',
            '["healthcare"]',
            '["tourism"~"hotel|guest_house|hostel|motel|camp_site|chalet|apartment"]',
            '["leisure"~"fitness_centre|sports_centre"]',
            '["amenity"~"restaurant|cafe|pub|bar|fast_food|pharmacy|clinic|doctors|dentist|veterinary|bank|post_office|library|community_centre|social_centre|childcare|kindergarten|school|fuel|car_rental|car_wash"]',
        ]
        clauses = []
        for filt in filters:
            for kind in ("node", "way", "relation"):
                clauses.append(f"{kind}{filt}(around:{radius},{lat},{lon});")
        return "[out:json][timeout:40];(" + "".join(clauses) + ");out center tags;"


def _ordered_endpoints(configured: str) -> list[str]:
    ordered = [configured, *DEFAULT_OVERPASS_ENDPOINTS]
    result: list[str] = []
    for endpoint in ordered:
        cleaned = endpoint.strip().rstrip("/")
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


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
    kinds = [
        tags.get("shop"), tags.get("amenity"), tags.get("craft"), tags.get("office"),
        tags.get("healthcare"), tags.get("tourism"), tags.get("leisure"),
    ]
    kind = next((k for k in kinds if k), "local place").replace("_", " ")
    return f"OpenStreetMap-listed {kind}; operational details should be checked with the provider."
