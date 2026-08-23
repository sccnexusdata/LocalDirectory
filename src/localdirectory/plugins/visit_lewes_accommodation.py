from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode


class VisitLewesAccommodationPlugin:
    """Discover accommodation explicitly listed by Visit Lewes.

    Visit Lewes is used as a corroborative tourism-directory source (class C),
    not as sole proof of facilities, availability or quality. Records are always
    categorised as accommodation because the source page itself is an explicit
    accommodation surface; venue-name inference (for example any business named
    "Inn") is deliberately forbidden.
    """

    name = "visit_lewes_accommodation"

    def __init__(self, index_urls: list[str], *, timeout: int = 20, user_agent: str = "LocalDirectory/0.1", max_results: int = 120, max_workers: int = 4):
        self.index_urls = [str(v).strip() for v in index_urls if str(v).strip()]
        self.timeout = int(timeout)
        self.user_agent = user_agent
        self.max_results = max(0, int(max_results))
        self.max_workers = max(1, min(int(max_workers), 8))

    def harvest(self) -> HarvestResult:
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        detail_urls: set[str] = set()
        requests_made = 0
        index_failures = 0
        for index_url in self.index_urls:
            try:
                response = requests.get(index_url, headers=headers, timeout=self.timeout)
                requests_made += 1
                response.raise_for_status()
                detail_urls.update(_detail_urls(response.text, response.url))
            except requests.RequestException:
                index_failures += 1
        urls = sorted(detail_urls)
        if self.max_results:
            urls = urls[: self.max_results]
        else:
            urls = []
        if not urls:
            return HarvestResult(self.name, ok=False, message=f"No accommodation detail URLs discovered; {index_failures} index failure(s)", requests_made=requests_made)

        records: list[ListingRecord] = []
        parse_failures = 0
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(urls))) as executor:
            for record in executor.map(lambda u: self._fetch_detail(u, headers), urls):
                requests_made += 1
                if record is None:
                    parse_failures += 1
                else:
                    records.append(record)
        return HarvestResult(
            self.name,
            records=records,
            ok=bool(records),
            message=f"Harvested {len(records)} explicit accommodation records from {len(urls)} Visit Lewes detail pages; {parse_failures} detail failure(s)",
            requests_made=requests_made,
        )

    def _fetch_detail(self, url: str, headers: dict[str, str]) -> ListingRecord | None:
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return None
        return _parse_detail(response.text, response.url)


def _detail_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.casefold()
    found: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor.get("href") or ""))
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() != host:
            continue
        if re.search(r"/accommodation/[^?#]+-p\d+/?$", parsed.path, flags=re.I):
            found.add(parsed._replace(query="", fragment="").geturl().rstrip("/"))
    return sorted(found)


def _text_parent_with_postcode(soup: BeautifulSoup) -> tuple[str, str]:
    postcode_re = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
    for node in soup.find_all(string=postcode_re):
        parent = node.parent
        text = " ".join(parent.stripped_strings) if parent else str(node)
        match = postcode_re.search(text)
        if match:
            return text.strip(), normalise_postcode(match.group(0))
    full = " ".join(soup.stripped_strings)
    match = postcode_re.search(full)
    return ("", normalise_postcode(match.group(0))) if match else ("", "")


def _external_website(soup: BeautifulSoup, source_url: str) -> str:
    source_host = urlparse(source_url).netloc.casefold()
    preferred = []
    fallback = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, str(anchor.get("href") or "")).strip()
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if parsed.netloc.casefold() == source_host:
            continue
        label = " ".join(anchor.stripped_strings).casefold()
        if "website" in label or "visit website" in label:
            preferred.append(href)
        else:
            fallback.append(href)
    return (preferred or fallback or [""])[0]


def _type_text(soup: BeautifulSoup) -> str:
    full = " ".join(soup.stripped_strings)
    match = re.search(r"\bType\s*:\s*([^|]{2,60}?)(?=\s{2,}|\s(?:Address|About|Website|Email|Tel)\b)", full, flags=re.I)
    return match.group(1).strip() if match else "Accommodation"


def _parse_detail(html: str, source_url: str) -> ListingRecord | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    name = " ".join(heading.stripped_strings).strip() if heading else ""
    if not name or name.casefold() in {"accommodation", "visit lewes"}:
        return None
    address, postcode = _text_parent_with_postcode(soup)
    if not postcode:
        return None
    accommodation_type = _type_text(soup)
    website = _external_website(soup, source_url)
    description = f"{accommodation_type}. Accommodation identity corroborated by Visit Lewes; check current facilities, prices and availability with the provider."
    source = SourceRef(
        source_name="visit_lewes_accommodation",
        source_type="official_tourism_directory",
        source_class="C",
        source_id=source_url.rstrip("/").rsplit("/", 1)[-1],
        source_url=source_url,
    )
    record = ListingRecord(
        name=name,
        listing_type="place",
        primary_category="accommodation",
        description=description,
        website=website,
        address=address,
        postcode=postcode,
        sources=[source],
        quality_flags=["accommodation_facilities_not_independently_verified"],
        field_provenance={
            "name": ["visit_lewes_accommodation"],
            "primary_category": ["visit_lewes_accommodation"],
            "address": ["visit_lewes_accommodation"],
            "postcode": ["visit_lewes_accommodation"],
            **({"website": ["visit_lewes_accommodation"]} if website else {}),
        },
    )
    return record
