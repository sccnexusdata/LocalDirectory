from __future__ import annotations

import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.text import normalise_postcode


CATEGORY_SLUGS = {
    "bed-and-breakfasts",
    "self-catering",
    "hotels",
    "pubs-and-inns",
    "camping-and-caravanning",
    "camping",
    "caravanning",
    "lewes",
    "villages",
    "newhaven",
    "seaford",
    "pet-friendly",
    "dog-friendly",
    "accessible",
    "family-friendly",
    "special-offers",
    "last-minute",
}

BLOCKED_PROVIDER_HOST_FRAGMENTS = {
    "booking.com",
    "direct-book.com",
    "expedia.",
    "hotels.com",
    "tripadvisor.",
    "airbnb.",
    "facebook.",
    "instagram.",
    "x.com",
    "twitter.",
    "youtube.",
    "google.",
    "simplevieweurope.com",
    "simpleviewinc.com",
    "simpleviewcms.com",
}

ACCOMMODATION_EVIDENCE = (
    "book a room",
    "book your room",
    "book your stay",
    "stay with us",
    "our rooms",
    "guest rooms",
    "bedrooms",
    "bed and breakfast",
    "bed & breakfast",
    "guest accommodation",
    "self catering",
    "self-catering",
    "holiday cottage",
    "holiday accommodation",
    "hotel",
    "campsite",
    "camp site",
    "camping",
    "glamping",
    "lodges",
)

STOPWORDS = {
    "the",
    "and",
    "hotel",
    "inn",
    "pub",
    "rooms",
    "room",
    "accommodation",
    "lewes",
    "sussex",
    "east",
    "at",
    "of",
    "in",
    "a",
    "an",
}


class VisitLewesAccommodationPlugin:
    """Discover explicit accommodation and seek provider-owned corroboration.

    Visit Lewes is Class C discovery/corroboration. An external provider website
    is added as Class B only when the Visit Lewes link is explicitly labelled as
    a website and the provider site itself matches the venue identity and contains
    explicit accommodation language.
    """

    name = "visit_lewes_accommodation"

    def __init__(
        self,
        index_urls: list[str],
        *,
        timeout: int = 20,
        user_agent: str = "LocalDirectory/0.1",
        max_results: int = 160,
        max_workers: int = 4,
        max_pages_per_index: int = 4,
    ):
        self.index_urls = [str(value).strip() for value in index_urls if str(value).strip()]
        self.timeout = int(timeout)
        self.user_agent = user_agent
        self.max_results = max(0, int(max_results))
        self.max_workers = max(1, min(int(max_workers), 8))
        self.max_pages_per_index = max(1, min(int(max_pages_per_index), 8))

    def harvest(self) -> HarvestResult:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }
        detail_urls: set[str] = set()
        requests_made = 0
        index_failures = 0

        for index_url in self.index_urls:
            discovered, made, failed = self._discover_index(index_url, headers)
            detail_urls.update(discovered)
            requests_made += made
            index_failures += failed

        urls = sorted(detail_urls)
        if self.max_results:
            urls = urls[: self.max_results]
        else:
            urls = []

        if not urls:
            return HarvestResult(
                self.name,
                ok=False,
                message=f"No accommodation detail URLs discovered; {index_failures} index failure(s)",
                requests_made=requests_made,
            )

        records: list[ListingRecord] = []
        parse_failures = 0
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(urls))) as executor:
            for record, made in executor.map(lambda url: self._fetch_detail(url, headers), urls):
                requests_made += made
                if record is None:
                    parse_failures += 1
                else:
                    records.append(record)

        provider_verified = sum(
            1
            for record in records
            if any(source.source_class.upper() == "B" for source in record.sources)
        )
        return HarvestResult(
            self.name,
            records=records,
            ok=bool(records),
            message=(
                f"Harvested {len(records)} explicit accommodation records from "
                f"{len(urls)} Visit Lewes detail pages; "
                f"{provider_verified} provider-owned corroboration(s); "
                f"{parse_failures} detail failure(s); {index_failures} index failure(s)"
            ),
            requests_made=requests_made,
        )

    def _discover_index(
        self,
        index_url: str,
        headers: dict[str, str],
    ) -> tuple[set[str], int, int]:
        pending = deque([index_url])
        visited: set[str] = set()
        details: set[str] = set()
        requests_made = 0
        failures = 0
        origin_path = urlparse(index_url).path.rstrip("/")

        while pending and len(visited) < self.max_pages_per_index:
            url = pending.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
                requests_made += 1
                response.raise_for_status()
            except requests.RequestException:
                failures += 1
                continue

            details.update(_detail_urls(response.text, response.url))
            for page_url in _pagination_urls(response.text, response.url, origin_path):
                if page_url not in visited and page_url not in pending:
                    pending.append(page_url)

        return details, requests_made, failures

    def _fetch_detail(
        self,
        url: str,
        headers: dict[str, str],
    ) -> tuple[ListingRecord | None, int]:
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return None, 1

        record = _parse_detail(response.text, response.url)
        requests_made = 1
        if record is None or not record.website:
            return record, requests_made

        verified, made = _verify_provider_website(
            record.name,
            record.website,
            headers,
            self.timeout,
        )
        requests_made += made
        if verified:
            record.sources.append(
                SourceRef(
                    source_name="provider_website",
                    source_type="organisation_owned_website",
                    source_class="B",
                    source_id=urlparse(record.website).netloc.casefold(),
                    source_url=record.website,
                )
            )
            record.field_provenance.setdefault("primary_category", []).append(
                "provider_website"
            )
            record.field_provenance.setdefault("website", []).append("provider_website")
            record.quality_flags = [
                flag
                for flag in record.quality_flags
                if flag != "accommodation_provider_not_yet_corroborated"
            ]
            record.quality_flags.append("accommodation_provider_owned_site_corroborated")
        return record, requests_made


def _detail_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.casefold()
    found: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor.get("href") or ""))
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() != host:
            continue
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) != 2 or parts[0].casefold() != "accommodation":
            continue
        slug = parts[1].casefold()
        if slug in CATEGORY_SLUGS:
            continue
        found.add(parsed._replace(query="", fragment="").geturl().rstrip("/"))
    return sorted(found)


def _pagination_urls(html: str, base_url: str, origin_path: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.casefold()
    found: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor.get("href") or ""))
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() != host or parsed.path.rstrip("/") != origin_path:
            continue
        page = parse_qs(parsed.query).get("p", [])
        if page and str(page[0]).isdigit():
            found.add(parsed._replace(fragment="").geturl())
    return sorted(found)


def _text_parent_with_postcode(soup: BeautifulSoup) -> tuple[str, str]:
    postcode_re = re.compile(
        r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
        re.IGNORECASE,
    )
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
    """Return only an explicitly labelled provider website link."""
    source_host = urlparse(source_url).netloc.casefold()
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.stripped_strings).casefold()
        if "website" not in label:
            continue
        href = urljoin(source_url, str(anchor.get("href") or "")).strip()
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        host = parsed.netloc.casefold()
        if host == source_host:
            continue
        if any(fragment in host for fragment in BLOCKED_PROVIDER_HOST_FRAGMENTS):
            continue
        return href
    return ""


def _type_text(soup: BeautifulSoup) -> str:
    for node in soup.find_all(string=re.compile(r"\bType\s*:", re.IGNORECASE)):
        text = " ".join(node.parent.stripped_strings) if node.parent else str(node)
        match = re.search(
            r"\bType\s*:\s*(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            value = match.group(1).strip()
            if 1 < len(value) <= 80:
                return value
    return "Accommodation"


def _provider_identity_tokens(name: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", name.casefold())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _provider_supports_accommodation(name: str, html: str) -> bool:
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings).casefold()
    if not any(term in text for term in ACCOMMODATION_EVIDENCE):
        return False
    tokens = _provider_identity_tokens(name)
    if not tokens:
        return False
    overlap = tokens & set(re.findall(r"[a-z0-9]+", text))
    return bool(overlap) and len(overlap) >= max(1, min(2, len(tokens)))


def _verify_provider_website(
    name: str,
    website: str,
    headers: dict[str, str],
    timeout: int,
) -> tuple[bool, int]:
    parsed = urlparse(website)
    host = parsed.netloc.casefold()
    if parsed.scheme not in {"http", "https"} or not host:
        return False, 0
    if any(fragment in host for fragment in BLOCKED_PROVIDER_HOST_FRAGMENTS):
        return False, 0
    try:
        response = requests.get(website, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return False, 1
    return _provider_supports_accommodation(name, response.text), 1


def _parse_detail(html: str, source_url: str) -> ListingRecord | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    name = " ".join(heading.stripped_strings).strip() if heading else ""
    if not name or name.casefold() in {"accommodation", "visit lewes"}:
        return None

    slug = source_url.rstrip("/").rsplit("/", 1)[-1].casefold()
    if slug in CATEGORY_SLUGS:
        return None

    address, postcode = _text_parent_with_postcode(soup)
    if not postcode:
        return None

    accommodation_type = _type_text(soup)
    page_text = " ".join(soup.stripped_strings).casefold()
    if not (
        accommodation_type.casefold() != "accommodation"
        or any(term in page_text for term in ACCOMMODATION_EVIDENCE)
    ):
        return None

    website = _external_website(soup, source_url)
    source = SourceRef(
        source_name="visit_lewes_accommodation",
        source_type="official_tourism_directory",
        source_class="C",
        source_id=slug,
        source_url=source_url,
    )
    return ListingRecord(
        name=name,
        listing_type="place",
        primary_category="accommodation",
        description=(
            f"{accommodation_type}. Accommodation identity listed by Visit Lewes; "
            "check current facilities, prices and availability with the provider."
        ),
        website=website,
        address=address,
        postcode=postcode,
        sources=[source],
        quality_flags=["accommodation_provider_not_yet_corroborated"],
        field_provenance={
            "name": ["visit_lewes_accommodation"],
            "primary_category": ["visit_lewes_accommodation"],
            "address": ["visit_lewes_accommodation"],
            "postcode": ["visit_lewes_accommodation"],
            **({"website": ["visit_lewes_accommodation"]} if website else {}),
        },
    )
