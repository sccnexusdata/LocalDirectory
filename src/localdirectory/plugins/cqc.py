from __future__ import annotations

import csv
import io
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from localdirectory.geospatial import within_radius
from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode


DEFAULT_INDEX_URL = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"


class CQCPlugin:
    """Harvest current CQC-regulated health and social-care locations."""

    name = "cqc"

    def __init__(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        postcode_area: str = "",
        *,
        index_url: str = DEFAULT_INDEX_URL,
        csv_url: str = "",
        timeout: int = 45,
        user_agent: str = "LocalDirectory/0.1",
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.radius_km = radius_km
        self.postcode_area = postcode_area.strip().upper()
        self.index_url = index_url
        self.csv_url = csv_url
        self.timeout = timeout
        self.user_agent = user_agent

    def harvest(self) -> HarvestResult:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,text/csv;q=0.9,*/*;q=0.8",
        }
        requests_made = 0
        csv_url = self.csv_url
        if not csv_url:
            response = requests.get(self.index_url, headers=headers, timeout=self.timeout)
            requests_made += 1
            response.raise_for_status()
            csv_url = _discover_csv_url(response.text, response.url)
            if not csv_url:
                return HarvestResult(
                    self.name,
                    ok=False,
                    message="CQC care-directory CSV link was not found on the data page",
                    requests_made=requests_made,
                )

        response = requests.get(csv_url, headers=headers, timeout=self.timeout)
        requests_made += 1
        response.raise_for_status()
        records = _parse_directory_csv(
            response.content,
            centre_latitude=self.latitude,
            centre_longitude=self.longitude,
            radius_km=self.radius_km,
            postcode_area=self.postcode_area,
        )
        return HarvestResult(
            self.name,
            records,
            True,
            f"Harvested {len(records)} current CQC-regulated local locations from {csv_url}",
            requests_made,
        )


def _discover_csv_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or "").strip())
        text = anchor.get_text(" ", strip=True).casefold()
        lower_href = href.casefold()
        score = 0
        if "cqc care directory" in text and "csv" in text:
            score += 10
        if lower_href.endswith(".csv"):
            score += 4
        if "directory" in lower_href and "csv" in lower_href:
            score += 2
        if "archive" in text or "deactivated" in text:
            score -= 10
        if score > 0:
            candidates.append((score, href))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _decode_directory(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    sample = raw[:4096]
    if sample and sample.count(b"\x00") > len(sample) // 8:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _dialect(text: str) -> csv.Dialect:
    sample = text[:65536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        return csv.excel


def _parse_directory_csv(
    raw: bytes,
    *,
    centre_latitude: float,
    centre_longitude: float,
    radius_km: float,
    postcode_area: str,
) -> list[ListingRecord]:
    text = _decode_directory(raw)
    if "<html" in text[:1000].casefold() or "<!doctype html" in text[:1000].casefold():
        raise ValueError("CQC directory download returned HTML instead of CSV data")
    dialect = _dialect(text)
    rows = list(csv.reader(io.StringIO(text), dialect=dialect))
    header_index = _header_index(rows)
    if header_index is None:
        preview = " | ".join(" / ".join(row[:4]) for row in rows[:3])[:400]
        raise ValueError(f"CQC directory header row was not found; preview={preview!r}")

    header = rows[header_index]
    data = _rows_to_csv([header, *rows[header_index + 1 :]], dialect.delimiter)
    reader = csv.DictReader(io.StringIO(data), delimiter=dialect.delimiter)
    records: list[ListingRecord] = []
    for row in reader:
        record = _record_from_row(
            row,
            centre_latitude=centre_latitude,
            centre_longitude=centre_longitude,
            radius_km=radius_km,
            postcode_area=postcode_area,
        )
        if record:
            records.append(record)
    return records


def _normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _rows_to_csv(rows: list[list[str]], delimiter: str = ",") -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerows(rows)
    return output.getvalue()


def _header_index(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows[:50]):
        normalised = {_normalise_header(cell) for cell in row}
        if "locationid" in normalised and "locationname" in normalised:
            return index
    return None


def _record_from_row(
    row: dict[str, str],
    *,
    centre_latitude: float,
    centre_longitude: float,
    radius_km: float,
    postcode_area: str,
) -> ListingRecord | None:
    name = _field(row, "Location Name", "Name")
    location_id = _field(row, "Location ID", "CQC Location ID")
    postcode = normalise_postcode(_field(row, "Location Postal Code", "Postcode", "Location Postcode"))
    if not name or not location_id:
        return None

    latitude = _float(_field(row, "Location Latitude", "Latitude"))
    longitude = _float(_field(row, "Location Longitude", "Longitude"))
    in_radius = within_radius(latitude, longitude, centre_latitude, centre_longitude, radius_km)
    postcode_match = bool(postcode_area and postcode.upper().startswith(postcode_area.upper()))
    if not in_radius and not (latitude is None and longitude is None and postcode_match):
        return None

    service_text = " ".join(
        value
        for value in [
            _field(row, "Location Type/Sector", "Location Type"),
            _field(row, "Location Primary Inspection Category", "Primary Inspection Category"),
            _field(row, "Service Types", "Location Service Types"),
        ]
        if value
    ).strip()
    remote_service = _is_remote_service(service_text)
    address = _address(row)
    website = _field(row, "Location Web Address", "Location Website", "Website")
    phone = _field(row, "Location Telephone Number", "Telephone", "Phone")
    provider_company = re.sub(r"\s+", "", _field(row, "Provider Companies House Number"))
    provider_charity = re.sub(r"\s+", "", _field(row, "Provider Charity Number"))
    source_url = f"https://www.cqc.org.uk/location/{location_id}"

    description_kind = service_text or "health or social care service"
    description = (
        f"CQC-registered {description_kind}. Check the CQC record and provider directly for current "
        "service scope, ratings and availability."
    )

    regulator_ids = {"cqc": location_id}
    if provider_charity:
        regulator_ids["charity_commission"] = provider_charity

    return ListingRecord(
        name=name,
        listing_type="service_provider" if remote_service else "place",
        primary_category="health_care",
        description=description,
        website=website,
        phone=phone,
        email="",
        address=address,
        postcode=postcode,
        latitude=None if remote_service else latitude,
        longitude=None if remote_service else longitude,
        service_area=["Lewes"] if remote_service else [],
        company_number=provider_company,
        regulator_ids=regulator_ids,
        sources=[SourceRef("Care Quality Commission", "official_register", "A", source_id=location_id, source_url=source_url)],
        address_public=not remote_service,
        phone_public=True,
        email_public=False,
        review_required=True,
        quality_flags=["cqc_service_office_not_mapped"] if remote_service else [],
    )


def _field(row: dict[str, str], *keys: str) -> str:
    by_key = {
        _normalise_header(str(key)): str(value or "").strip()
        for key, value in row.items()
        if key is not None
    }
    for key in keys:
        value = by_key.get(_normalise_header(key), "")
        if value:
            return value
    return ""


def _float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _address(row: dict[str, str]) -> str:
    parts = [
        _field(row, "Location Street Address", "Street Address"),
        _field(row, "Location Address Line 2", "Address Line 2"),
        _field(row, "Location City", "City", "Town"),
        _field(row, "Location County", "County"),
        _field(row, "Location Postal Code", "Postcode", "Location Postcode"),
    ]
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        cleaned = part.strip(" ,")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return ", ".join(result)


def _is_remote_service(value: str) -> bool:
    text = value.casefold().replace("-", " ")
    terms = (
        "homecare",
        "home care",
        "domiciliary",
        "community service",
        "community healthcare",
        "supported living",
        "care agency",
    )
    return any(term in text for term in terms)
