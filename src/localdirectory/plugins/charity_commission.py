from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from localdirectory.geospatial import within_radius
from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode


DEFAULT_INDEX_URL = "https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download"
DEFAULT_POSTCODE_ENDPOINT = "https://api.postcodes.io/postcodes"


class CharityCommissionPlugin:
    """Harvest registered charities whose public contact postcode is local."""

    name = "charity_commission"

    def __init__(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        candidate_postcode_prefixes: list[str],
        *,
        index_url: str = DEFAULT_INDEX_URL,
        zip_url: str = "",
        postcode_endpoint: str = DEFAULT_POSTCODE_ENDPOINT,
        timeout: int = 45,
        user_agent: str = "LocalDirectory/0.1",
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.radius_km = radius_km
        self.candidate_postcode_prefixes = tuple(
            prefix.strip().upper() for prefix in candidate_postcode_prefixes if prefix.strip()
        )
        self.index_url = index_url
        self.zip_url = zip_url
        self.postcode_endpoint = postcode_endpoint
        self.timeout = timeout
        self.user_agent = user_agent

    def harvest(self) -> HarvestResult:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json,text/html,*/*"}
        requests_made = 0
        zip_url = self.zip_url
        if not zip_url:
            response = requests.get(self.index_url, headers=headers, timeout=self.timeout)
            requests_made += 1
            response.raise_for_status()
            zip_url = _discover_charity_zip_url(response.text, response.url)
            if not zip_url:
                return HarvestResult(
                    self.name,
                    ok=False,
                    message="Charity Commission charity extract link was not found",
                    requests_made=requests_made,
                )

        response = requests.get(zip_url, headers=headers, timeout=self.timeout)
        requests_made += 1
        response.raise_for_status()
        rows = _read_charity_rows(response.content)
        candidates = _candidate_rows(rows, self.candidate_postcode_prefixes)
        postcodes = sorted(
            {
                normalise_postcode(str(row.get("charity_contact_postcode") or ""))
                for row in candidates
            }
        )
        postcodes = [postcode for postcode in postcodes if postcode]
        resolved, postcode_requests = _resolve_postcodes(
            postcodes,
            endpoint=self.postcode_endpoint,
            timeout=min(self.timeout, 25),
            user_agent=self.user_agent,
        )
        requests_made += postcode_requests
        records = _records_from_rows(
            candidates,
            resolved,
            centre_latitude=self.latitude,
            centre_longitude=self.longitude,
            radius_km=self.radius_km,
        )
        message = (
            f"Harvested {len(records)} registered local charities from {len(candidates)} postcode-prefiltered "
            f"candidates; resolved {len(resolved)}/{len(postcodes)} postcodes"
        )
        return HarvestResult(self.name, records, True, message, requests_made)


def _discover_charity_zip_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or "").strip())
        lower_href = href.casefold()
        if ".zip" not in lower_href:
            continue
        anchor_text = anchor.get_text(" ", strip=True).casefold()
        parent = anchor.find_parent("tr")
        row_text = parent.get_text(" ", strip=True).casefold() if parent else ""
        score = 0
        if "charity" in lower_href:
            score += 8
        if "charity" in row_text:
            score += 5
        if "/json/" in lower_href or "json" in lower_href:
            score += 20
        elif "json" in anchor_text and "text" not in anchor_text:
            score += 10
        if "/text/" in lower_href or "tab" in anchor_text or "text" in anchor_text:
            score -= 3
        if any(term in lower_href for term in ("annual", "classification", "trustee", "history", "area_of_operation")):
            score -= 20
        if score > 0:
            candidates.append((score, href))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return candidates[0][1]


def _normalise_row_keys(row: dict) -> dict:
    return {
        str(key).strip().casefold().replace(" ", "_"): value
        for key, value in row.items()
        if key is not None
    }


def _read_charity_rows(raw_zip: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        json_names = [name for name in names if name.casefold().endswith(".json")]
        if json_names:
            ranked = sorted(
                json_names,
                key=lambda name: (
                    0 if "charity" in name.casefold() else 1,
                    1 if any(term in name.casefold() for term in ("annual", "classification", "trustee", "history")) else 0,
                    len(name),
                    name,
                ),
            )
            with archive.open(ranked[0]) as handle:
                payload = json.load(io.TextIOWrapper(handle, encoding="utf-8-sig"))
            if not isinstance(payload, list):
                raise TypeError("Charity Commission charity extract was not a JSON list")
            return [_normalise_row_keys(row) for row in payload if isinstance(row, dict)]

        text_names = [
            name
            for name in names
            if name.casefold().endswith((".txt", ".tsv", ".csv", ".bcp"))
            and "charity" in name.casefold()
            and not any(term in name.casefold() for term in ("annual", "classification", "trustee", "history"))
        ]
        if not text_names:
            raise ValueError("Charity Commission ZIP contained neither charity JSON nor tab-delimited text")
        text_names.sort(key=lambda name: (len(name), name))
        with archive.open(text_names[0]) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace")
            reader = csv.DictReader(text, delimiter="\t")
            rows = [_normalise_row_keys(row) for row in reader if isinstance(row, dict)]
        if not rows:
            raise ValueError("Charity Commission tab-delimited charity extract contained no data rows")
        return rows


def _candidate_rows(rows: list[dict], prefixes: tuple[str, ...]) -> list[dict]:
    allowed_outward_codes = {prefix.replace(" ", "").upper() for prefix in prefixes}
    candidates: list[dict] = []
    for row in rows:
        status = str(row.get("charity_registration_status") or row.get("reg_status") or "").strip().casefold()
        if status not in {"registered", "r"}:
            continue
        linked = str(row.get("linked_charity_number") or row.get("group_subsid_suffix") or "0").strip()
        if linked not in {"", "0", "0.0"}:
            continue
        postcode = normalise_postcode(str(row.get("charity_contact_postcode") or ""))
        if not postcode:
            continue
        outward_code = postcode.split(" ", 1)[0].upper()
        if allowed_outward_codes and outward_code not in allowed_outward_codes:
            continue
        candidates.append(row)
    return candidates


def _chunks(values: list[str], size: int = 100) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _resolve_postcodes(
    postcodes: list[str],
    *,
    endpoint: str,
    timeout: int,
    user_agent: str,
) -> tuple[dict[str, tuple[float, float]], int]:
    resolved: dict[str, tuple[float, float]] = {}
    requests_made = 0
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": user_agent}
    for batch in _chunks(postcodes):
        try:
            response = requests.post(endpoint, json={"postcodes": batch}, headers=headers, timeout=timeout)
            requests_made += 1
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            continue
        for item in payload.get("result", []) if isinstance(payload, dict) else []:
            postcode = normalise_postcode(str((item or {}).get("query") or ""))
            result = (item or {}).get("result") or {}
            try:
                latitude = float(result.get("latitude"))
                longitude = float(result.get("longitude"))
            except (TypeError, ValueError):
                continue
            if postcode:
                resolved[postcode] = (latitude, longitude)
    return resolved, requests_made


def _records_from_rows(
    rows: list[dict],
    postcode_coordinates: dict[str, tuple[float, float]],
    *,
    centre_latitude: float,
    centre_longitude: float,
    radius_km: float,
) -> list[ListingRecord]:
    records: list[ListingRecord] = []
    for row in rows:
        postcode = normalise_postcode(str(row.get("charity_contact_postcode") or ""))
        coordinates = postcode_coordinates.get(postcode)
        if not coordinates or not within_radius(
            coordinates[0], coordinates[1], centre_latitude, centre_longitude, radius_km
        ):
            continue
        name = str(row.get("charity_name") or "").strip()
        organisation_number = str(row.get("organisation_number") or "").strip()
        registered_number = str(row.get("registered_charity_number") or row.get("reg_charity_number") or "").strip()
        if not name or not (organisation_number or registered_number):
            continue
        company_number = str(row.get("charity_company_registration_number") or "").strip()
        website = _normalise_website(str(row.get("charity_contact_web") or ""))
        address = _contact_address(row, postcode)
        source_id = registered_number or organisation_number
        source_url = (
            "https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/"
            f"{organisation_number or registered_number}"
        )
        records.append(
            ListingRecord(
                name=name,
                listing_type="service_provider",
                primary_category="community_charities",
                description=(
                    "Registered charity with a Charity Commission contact postcode within the configured local radius. "
                    "The registered contact address is not treated as a visitor or service location; check the charity's "
                    "official website and register entry for current activities and contact details."
                ),
                website=website,
                address=address,
                postcode=postcode,
                company_number=company_number,
                regulator_ids={"charity_commission": registered_number or organisation_number},
                sources=[
                    SourceRef(
                        "Charity Commission for England and Wales",
                        "official_register",
                        "A",
                        source_id=source_id,
                        source_url=source_url,
                    )
                ],
                address_public=False,
                phone_public=False,
                email_public=False,
                review_required=True,
                quality_flags=["charity_contact_address_not_assumed_service_location"],
            )
        )
    return records


def _normalise_website(value: str) -> str:
    website = value.strip()
    if not website:
        return ""
    if website.casefold().startswith(("http://", "https://")):
        return website
    if website.casefold().startswith("www."):
        return f"https://{website}"
    return ""


def _contact_address(row: dict, postcode: str) -> str:
    values = [str(row.get(f"charity_contact_address{index}") or "").strip() for index in range(1, 6)]
    values.append(postcode)
    seen: set[str] = set()
    parts: list[str] = []
    for value in values:
        cleaned = value.strip(" ,")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            parts.append(cleaned)
    return ", ".join(parts)
