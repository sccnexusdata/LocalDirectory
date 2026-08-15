from __future__ import annotations

import json
from typing import ClassVar
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.taxonomy import category_from_terms
from localdirectory.text import normalise_postcode


class JSONLDPlugin:
    name = "json_ld"
    TYPES: ClassVar[set[str]] = {
        "LocalBusiness",
        "Organization",
        "ProfessionalService",
        "Store",
        "Restaurant",
        "FoodEstablishment",
        "CafeOrCoffeeShop",
        "FastFoodRestaurant",
        "Bakery",
        "BarOrPub",
        "Brewery",
        "Winery",
        "LodgingBusiness",
        "BedAndBreakfast",
        "Hostel",
        "Hotel",
        "Motel",
        "Campground",
        "MedicalBusiness",
        "Dentist",
        "Pharmacy",
        "Physician",
        "VeterinaryCare",
        "HealthAndBeautyBusiness",
        "BeautySalon",
        "HairSalon",
        "NailSalon",
        "DaySpa",
        "HealthClub",
        "HomeAndConstructionBusiness",
        "Electrician",
        "GeneralContractor",
        "HVACBusiness",
        "HousePainter",
        "Locksmith",
        "Plumber",
        "RoofingContractor",
        "LegalService",
        "AccountingService",
        "FinancialService",
        "RealEstateAgent",
        "AutomotiveBusiness",
        "AutoRepair",
        "AutoPartsStore",
        "AutoDealer",
        "AutoRental",
        "ChildCare",
        "Library",
        "GovernmentOffice",
        "PostOffice",
        "SportsActivityLocation",
        "TravelAgency",
        "TouristInformationCenter",
    }

    def __init__(self, urls: list[str], timeout: int = 30, user_agent: str = "LocalDirectory/0.1"):
        self.urls = [u for u in urls if u]
        self.timeout = timeout
        self.user_agent = user_agent

    def harvest(self) -> HarvestResult:
        records: list[ListingRecord] = []
        requests_made = 0
        errors: list[str] = []
        for url in self.urls:
            try:
                response = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=self.timeout)
                requests_made += 1
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                    try:
                        data = json.loads(script.string or script.get_text() or "null")
                    except json.JSONDecodeError:
                        continue
                    for obj in _objects(data):
                        record = _record(obj, response.url)
                        if record:
                            records.append(record)
            except requests.RequestException as exc:
                errors.append(f"{url}: {exc.__class__.__name__}")
        return HarvestResult(self.name, records, not (self.urls and len(errors) == len(self.urls)), "; ".join(errors) if errors else f"Harvested {len(records)} JSON-LD records", requests_made)


def _objects(data):
    if isinstance(data, list):
        for item in data:
            yield from _objects(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _objects(item)
        else:
            yield data


def _types(obj: dict) -> set[str]:
    value = obj.get("@type", [])
    if isinstance(value, str):
        return {value}
    return {str(v) for v in value if v}


def _record(obj: dict, source_url: str) -> ListingRecord | None:
    if not (_types(obj) & JSONLDPlugin.TYPES):
        return None
    name = str(obj.get("name") or "").strip()
    if not name:
        return None
    address_obj = obj.get("address") or {}
    if isinstance(address_obj, str):
        address = address_obj
        postcode = ""
    else:
        parts = [address_obj.get("streetAddress"), address_obj.get("addressLocality"), address_obj.get("addressRegion"), address_obj.get("postalCode")]
        address = ", ".join(str(p).strip() for p in parts if p)
        postcode = normalise_postcode(str(address_obj.get("postalCode") or ""))
    geo = obj.get("geo") or {}
    lat = _float(geo.get("latitude")) if isinstance(geo, dict) else None
    lon = _float(geo.get("longitude")) if isinstance(geo, dict) else None
    website = str(obj.get("url") or source_url)
    return ListingRecord(
        name=name,
        listing_type="place" if address else "service_provider",
        primary_category=category_from_terms(*_types(obj), str(obj.get("description") or "")),
        description=str(obj.get("description") or "").strip(),
        website=urljoin(source_url, website),
        phone=str(obj.get("telephone") or "").strip(),
        email=str(obj.get("email") or "").replace("mailto:", "").strip(),
        address=address,
        postcode=postcode,
        latitude=lat,
        longitude=lon,
        sources=[SourceRef(name, "organisation_owned_website", "B", source_url=source_url)],
        review_required=True,
    )


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
