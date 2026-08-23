from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode
from localdirectory.plugins.visit_lewes_accommodation import ACCOMMODATION_EVIDENCE, _provider_supports_accommodation


PHONE_RE = re.compile(r"(?:\+44\s?\d{2,4}|0\d{2,4})[\s\d]{6,12}")
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)


class OwnedAccommodationPlugin:
    """Verify explicitly configured provider-owned accommodation websites.

    Seeds are intentionally explicit and bounded. They are useful for newly
    opened/reopened accommodation or providers absent from a tourism directory.
    The provider page must itself support the accommodation claim; a configured
    URL alone is not enough.
    """

    name = "owned_accommodation"

    def __init__(self, seeds: list[dict | str], *, timeout: int = 20, user_agent: str = "LocalDirectory/0.1"):
        self.seeds = seeds
        self.timeout = int(timeout)
        self.user_agent = user_agent

    def harvest(self) -> HarvestResult:
        records: list[ListingRecord] = []
        failures = 0
        requests_made = 0
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        for raw in self.seeds:
            if isinstance(raw, str):
                seed = {"url": raw, "name": ""}
            elif isinstance(raw, dict):
                seed = raw
            else:
                failures += 1
                continue
            url = str(seed.get("url") or "").strip()
            name_hint = str(seed.get("name") or "").strip()
            if urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc:
                failures += 1
                continue
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
                requests_made += 1
                response.raise_for_status()
            except requests.RequestException:
                failures += 1
                continue
            record = _parse_owned_accommodation(response.text, response.url, name_hint=name_hint)
            if record is None:
                failures += 1
            else:
                records.append(record)
        return HarvestResult(
            self.name,
            records=records,
            ok=bool(records) or not self.seeds,
            message=f"Verified {len(records)}/{len(self.seeds)} provider-owned accommodation seed(s); {failures} failure(s)",
            requests_made=requests_made,
        )


def _best_name(soup: BeautifulSoup, name_hint: str) -> str:
    if name_hint:
        return name_hint.strip()
    title = " ".join((soup.title.string or "").split()).strip() if soup.title and soup.title.string else ""
    if title:
        for separator in (" - ", " | ", " — ", " – "):
            if separator in title:
                title = title.split(separator, 1)[0].strip()
                break
        if 2 <= len(title) <= 90:
            return title
    heading = soup.find("h1")
    return " ".join(heading.stripped_strings).strip() if heading else ""


def _address_context(soup: BeautifulSoup) -> tuple[str, str]:
    for node in soup.find_all(string=POSTCODE_RE):
        candidates = [node.parent, getattr(node.parent, "parent", None)]
        for parent in candidates:
            if parent is None:
                continue
            text = " ".join(parent.stripped_strings).strip()
            match = POSTCODE_RE.search(text)
            if match and len(text) <= 240:
                return text, normalise_postcode(match.group(0))
    text = " ".join(soup.stripped_strings)
    match = POSTCODE_RE.search(text)
    if match:
        return match.group(0), normalise_postcode(match.group(0))
    return "", ""


def _phone(soup: BeautifulSoup) -> str:
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if href.casefold().startswith("tel:"):
            return href.split(":", 1)[1].strip()
    match = PHONE_RE.search(" ".join(soup.stripped_strings))
    return match.group(0).strip() if match else ""


def _parse_owned_accommodation(html: str, source_url: str, *, name_hint: str = "") -> ListingRecord | None:
    soup = BeautifulSoup(html, "html.parser")
    name = _best_name(soup, name_hint)
    if not name or not _provider_supports_accommodation(name, html):
        return None
    page_text = " ".join(soup.stripped_strings).casefold()
    if not any(term in page_text for term in ACCOMMODATION_EVIDENCE):
        return None
    address, postcode = _address_context(soup)
    phone = _phone(soup)
    source = SourceRef(
        source_name="owned_accommodation",
        source_type="organisation_owned_website",
        source_class="B",
        source_id=urlparse(source_url).netloc.casefold(),
        source_url=source_url,
    )
    return ListingRecord(
        name=name,
        listing_type="place" if address or postcode else "service_provider",
        primary_category="accommodation",
        description="Accommodation explicitly verified on the provider-owned website; check current facilities, prices and availability directly.",
        website=source_url,
        phone=phone,
        address=address,
        postcode=postcode,
        sources=[source],
        quality_flags=["accommodation_provider_owned_site_verified"],
        field_provenance={
            "name": ["owned_accommodation"],
            "primary_category": ["owned_accommodation"],
            "website": ["owned_accommodation"],
            **({"phone": ["owned_accommodation"]} if phone else {}),
            **({"address": ["owned_accommodation"], "postcode": ["owned_accommodation"]} if postcode else {}),
        },
    )
