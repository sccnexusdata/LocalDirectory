from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from localdirectory.models import ListingRecord, SourceRef
from localdirectory.plugins.base import HarvestResult
from localdirectory.taxonomy import category_from_terms
from localdirectory.text import normalise_postcode


DEFAULT_INDEX_URL = "https://www.leweschamber.co.uk/members-directory/"


@dataclass(slots=True)
class _MemberResult:
    record: ListingRecord | None
    error: str = ""


class LewesChamberPlugin:
    """Discover and corroborate current Lewes Chamber member businesses.

    The Chamber explicitly asks that member details are not used for unsolicited
    mass mailing/telephone marketing. This adapter therefore deliberately does
    not ingest Chamber-listed email addresses or phone numbers. It retains only
    business identity, sector, public business address, member page and any
    organisation website link. Contact details can subsequently be enriched from
    the organisation-owned website under the normal provenance rules.
    """

    name = "lewes_chamber"

    def __init__(
        self,
        index_url: str = DEFAULT_INDEX_URL,
        *,
        timeout: int = 20,
        user_agent: str = "LocalDirectory/0.1",
        max_results: int = 150,
        max_workers: int = 4,
    ):
        self.index_url = index_url
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_results = max(0, int(max_results))
        self.max_workers = max(1, min(int(max_workers), 8))

    def harvest(self) -> HarvestResult:
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        try:
            response = requests.get(self.index_url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            return HarvestResult(self.name, ok=False, message=f"Directory index failed: {exc.__class__.__name__}", requests_made=1)

        urls = _member_urls(response.text, response.url)
        requests_made = 1
        if not urls:
            sitemap_urls, sitemap_requests = self._discover_from_sitemaps(response.url, headers)
            urls = sitemap_urls
            requests_made += sitemap_requests
        if self.max_results:
            urls = urls[: self.max_results]
        else:
            urls = []

        if not urls:
            return HarvestResult(
                self.name,
                ok=False,
                message="No member detail URLs discovered from directory index or sitemaps",
                requests_made=requests_made,
            )

        records: list[ListingRecord] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(urls))) as executor:
            for result in executor.map(lambda url: self._fetch_member(url, headers), urls):
                if result.record:
                    records.append(result.record)
                if result.error:
                    errors.append(result.error)
        requests_made += len(urls)

        ok = bool(records)
        message = f"Harvested {len(records)} Lewes Chamber members from {len(urls)} detail pages"
        if errors:
            message += f"; {len(errors)} detail request/parser failure(s)"
        return HarvestResult(self.name, records, ok, message, requests_made)

    def _fetch_member(self, url: str, headers: dict[str, str]) -> _MemberResult:
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            record = _parse_member(response.text, response.url)
            if record is None:
                return _MemberResult(None, f"{url}: no business record parsed")
            return _MemberResult(record)
        except requests.RequestException as exc:
            return _MemberResult(None, f"{url}: {exc.__class__.__name__}")

    def _discover_from_sitemaps(self, base_url: str, headers: dict[str, str]) -> tuple[list[str], int]:
        origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
        pending = [urljoin(origin, "/wp-sitemap.xml"), urljoin(origin, "/sitemap_index.xml")]
        seen_documents: set[str] = set()
        members: set[str] = set()
        requests_made = 0

        while pending and len(seen_documents) < 12:
            sitemap_url = pending.pop(0)
            if sitemap_url in seen_documents:
                continue
            seen_documents.add(sitemap_url)
            try:
                response = requests.get(sitemap_url, headers=headers, timeout=self.timeout)
                requests_made += 1
                response.raise_for_status()
                root = ElementTree.fromstring(response.content)
            except (requests.RequestException, ElementTree.ParseError):
                continue
            for node in root.iter():
                if not node.tag.endswith("loc") or not node.text:
                    continue
                location = node.text.strip()
                if "/members-directory/" in location and _is_member_detail_url(location):
                    members.add(_canonical_url(location))
                elif location.endswith(".xml") and urlparse(location).netloc == urlparse(origin).netloc:
                    pending.append(location)
        return sorted(members), requests_made


def _canonical_url(value: str) -> str:
    parsed = urlparse(value.strip())
    return parsed._replace(
        scheme=parsed.scheme.casefold(),
        netloc=parsed.netloc.casefold(),
        query="",
        fragment="",
    ).geturl().rstrip("/") + "/"


def _is_member_detail_url(value: str) -> bool:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/")
    prefix = "/members-directory/"
    if not path.startswith(prefix.rstrip("/")):
        return False
    suffix = path[len(prefix.rstrip("/")):].strip("/")
    return bool(suffix and "/" not in suffix)


def _member_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.casefold()
    urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor.get("href") or ""))
        if urlparse(absolute).netloc.casefold() != base_host:
            continue
        if _is_member_detail_url(absolute):
            urls.add(_canonical_url(absolute))
    return sorted(urls)


def _parse_member(html: str, source_url: str) -> ListingRecord | None:
    soup = BeautifulSoup(html, "html.parser")
    name = _member_name(soup)
    if not name or name.casefold() in {"members directory", "member directory"}:
        return None

    sector_text = _sector_text(soup)
    address = _address_text(soup)
    postcode_match = re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", address, flags=re.IGNORECASE)
    postcode = normalise_postcode(postcode_match.group(0)) if postcode_match else ""
    website = _external_website(soup, source_url)
    description = _description(soup, name)
    category = category_from_terms(sector_text, description)

    return ListingRecord(
        name=name,
        listing_type="place" if address else "service_provider",
        primary_category=category,
        description=description,
        website=website,
        # Intentionally do not ingest Chamber-listed phone/email. See class docstring.
        phone="",
        email="",
        address=address,
        postcode=postcode,
        service_area=["Lewes"],
        sources=[
            SourceRef(
                "Lewes Chamber of Commerce",
                "trade_association_directory",
                "C",
                source_id=_canonical_url(source_url),
                source_url=_canonical_url(source_url),
            )
        ],
        review_required=True,
    )


def _member_name(soup: BeautifulSoup) -> str:
    selectors = (".cn-entry-name", ".fn", "main h1", "article h1", "h1")
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            value = element.get_text(" ", strip=True)
            if value:
                return value
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return re.sub(r"\s*[-–|].*$", "", title).strip()


def _sector_text(soup: BeautifulSoup) -> str:
    for selector in (".cn-categories", ".cn-category", "[class*='categor']"):
        elements = soup.select(selector)
        text = " ".join(element.get_text(" ", strip=True) for element in elements)
        if text:
            return re.sub(r"^\s*Sector\s*:\s*", "", text, flags=re.IGNORECASE)
    lines = _lines(soup)
    for index, line in enumerate(lines):
        if line.casefold().rstrip(":") == "sector":
            values: list[str] = []
            for candidate in lines[index + 1:index + 5]:
                if _looks_like_contact_or_heading(candidate):
                    break
                values.append(candidate)
            return " ".join(values)
    return ""


def _address_text(soup: BeautifulSoup) -> str:
    element = soup.select_one(".cn-address")
    if element:
        return _clean_address(element.get_text(", ", strip=True))
    lines = _lines(soup)
    for index, line in enumerate(lines):
        if line.casefold().rstrip(":") == "address":
            values: list[str] = []
            for candidate in lines[index + 1:index + 9]:
                if candidate.casefold().rstrip(":") == "sector":
                    break
                if _looks_like_contact_or_heading(candidate):
                    break
                values.append(candidate)
            return _clean_address(", ".join(values))
    return ""


def _external_website(soup: BeautifulSoup, source_url: str) -> str:
    source_host = urlparse(source_url).netloc.casefold()
    labelled: list[str] = []
    other: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, str(anchor.get("href") or "").strip())
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if parsed.netloc.casefold() == source_host:
            continue
        text = anchor.get_text(" ", strip=True).casefold()
        if any(domain in parsed.netloc.casefold() for domain in ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com")):
            continue
        if "website" in text or "web site" in text:
            labelled.append(href)
        else:
            other.append(href)
    candidates = labelled or other
    return candidates[0].rstrip("/") if candidates else ""


def _description(soup: BeautifulSoup, name: str) -> str:
    for container in (soup.select_one("main"), soup.select_one("article"), soup):
        if not container:
            continue
        for paragraph in container.find_all("p"):
            text = paragraph.get_text(" ", strip=True)
            if len(text) >= 40 and "unsolicited mass" not in text.casefold() and name.casefold() not in {"", text.casefold()}:
                return text[:1200]
    return "Current member of Lewes Chamber of Commerce; sector information is published on the Chamber member page."


def _lines(soup: BeautifulSoup) -> list[str]:
    return [re.sub(r"\s+", " ", text).strip() for text in soup.stripped_strings if text.strip()]


def _looks_like_contact_or_heading(value: str) -> bool:
    lower = value.casefold().strip()
    return (
        lower in {"image", "website", "facebook", "instagram", "linkedin", "twitter", "back to the business directory index"}
        or "@" in value
        or bool(re.fullmatch(r"[+\d][\d\s().-]{7,}", value))
    )


def _clean_address(value: str) -> str:
    parts = [part.strip(" ,") for part in re.split(r"\s*,\s*", value) if part.strip(" ,")]
    if parts and parts[-1].casefold() == "united kingdom":
        parts.pop()
    return ", ".join(parts)
