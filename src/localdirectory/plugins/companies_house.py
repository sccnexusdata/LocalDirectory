from __future__ import annotations

import os

import requests

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode


class CompaniesHousePlugin:
    name = "companies_house"
    endpoint = "https://api.company-information.service.gov.uk/advanced-search/companies"

    def __init__(self, location_name: str, api_key: str | None = None, timeout: int = 30, user_agent: str = "LocalDirectory/0.1", max_results: int = 500):
        self.location_name = location_name
        self.api_key = api_key or os.getenv("COMPANIES_HOUSE_API_KEY", "")
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_results = max_results

    def harvest(self) -> HarvestResult:
        if not self.api_key:
            return HarvestResult(self.name, ok=True, message="Skipped: COMPANIES_HOUSE_API_KEY not configured")
        response = requests.get(
            self.endpoint,
            params={"location": self.location_name, "company_status": "active", "size": min(self.max_results, 5000)},
            auth=(self.api_key, ""),
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        response.raise_for_status()
        records: list[ListingRecord] = []
        for item in response.json().get("items", []):
            address = item.get("registered_office_address") or {}
            number = str(item.get("company_number") or "")
            name = str(item.get("company_name") or "").strip()
            if not name:
                continue
            records.append(
                ListingRecord(
                    name=name,
                    listing_type="registered_company",
                    primary_category="business_professional",
                    description="Active company returned by Companies House location search; trading presence and public-facing service must be independently corroborated.",
                    address=_address(address),
                    postcode=normalise_postcode(str(address.get("postal_code") or "")),
                    company_number=number,
                    regulator_ids={"companies_house": number},
                    sources=[SourceRef("Companies House", "official_register", "A", number, f"https://find-and-update.company-information.service.gov.uk/company/{number}")],
                    address_public=False,
                    review_required=True,
                    publish_safe=False,
                    quality_flags=["registered_office_not_assumed_trading_address"],
                )
            )
        return HarvestResult(self.name, records, True, f"Harvested {len(records)} Companies House candidates", 1)


def _address(address: dict) -> str:
    keys = ["address_line_1", "address_line_2", "locality", "region", "postal_code", "country"]
    return ", ".join(str(address.get(key)).strip() for key in keys if address.get(key))
