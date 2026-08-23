from __future__ import annotations

import re
import time
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
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)


@dataclass(slots=True)
class _MemberResult:
    record: ListingRecord | None
    error: str = ""
    requests_made: int = 0


class LewesChamberPlugin:
    """Discover Lewes Chamber members without ingesting Chamber phone/email data."""

    name = "lewes_chamber"

    def __init__(
        self,
        index_url: str = DEFAULT_INDEX_URL,
        *,
        timeout: int = 20,
        user_agent: str = "LocalDirectory/0.1",
        max_results: int = 150,
        max_workers: int = 1,
    ):
        self.index_url = index_url
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_results = max(0, int(max_results))
        # Chamber has previously rate-limited concurrent detail fetches. Keep this
        # source deliberately low-volume even if an older config asks for more.
        self.max_workers = max(1, min(int(max_workers), 2))

    def _headers(self, browser: bool = False) -> dict[str, str]:
        return {
            "User-Agent": BROWSER_UA if browser else self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": self.index_url,
            "Cache-Control": "no-cache",
        }

    def _get(self, url: str) -> tuple[requests.Response | None, int, str]:
        attempts = 0
        last_error = ""
        for browser in (False, True):
            try:
                attempts += 1
                response = requests.get(url, headers=self._headers(browser), timeout=self.timeout)
                if response.status_code in {403, 429, 503} and not browser:
                    time.sleep(0.15)
                    continue
                response.raise_for_status()
                return response, attempts, ""
            except requests.RequestException as exc:
                last_error = exc.__class__.__name__
                if not browser:
                    time.sleep(0.15)
        return None, attempts, last_error or "request failed"

    def harvest(self) -> HarvestResult:
        response, requests_made, error = self._get(self.index_url)
        if response is None:
            return HarvestResult(
                self.name,
                ok=False,
                message=f"Directory index failed: {error}",
                requests_made=requests_made,
            )

        urls = _member_urls(response.text, response.url)
        if not urls:
            sitemap_urls, sitemap_requests = self._discover_from_sitemaps(response.url)
            urls = sitemap_urls
            requests_made += sitemap_requests
        urls = urls[: self.max_results] if self.max_results else []
        if not urls:
            return HarvestResult(
                self.name,
                ok=False,
                message="No member detail URLs discovered from directory index or sitemaps",
                requests_made=requests_made,
            )

        records: list[ListingRecord] = []
        errors: list[str] = []
        # Sequential fetching is intentional: 101-member harvests previously failed
        # wholesale when multiple Chamber detail pages were requested concurrently.
        for url in urls:
            result = self._fetch_member(url)
            requests_made += result.requests_made
            if result.record:
                records.append(result.record)
            if result.error:
                errors.append(result.error)
            time.sleep(0.03)

        message = f"Harvested {len(records)} Lewes Chamber members from {len(urls)} detail pages"
        if errors:
            message += f"; {len(errors)} detail request/parser failure(s)"
        if errors and not records:
            message += f"; first failure: {errors[0]}"
        return HarvestResult(self.name, records, bool(records), message, requests_made)

    def _fetch_member(self, url: str) -> _MemberResult:
        response, requests_made, error = self._get(url)
        if response is None:
            return _MemberResult(None, f"{url}: {error}", requests_made)
        record = _parse_member(response.text, response.url)
        if record is None:
            title = BeautifulSoup(response.text, "html.parser").title
            title_text = title.get_text(" ", strip=True) if title else "no title"
            return _MemberResult(None, f"{url}: no business record parsed ({title_text[:80]})", requests_made)
        return _MemberResult(record, requests_made=requests_made)

    def _discover_from_sitemaps(self, base_url: str) -> tuple[list[str], int]:
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
            response, made, _ = self._get(sitemap_url)
            requests_made += made
            if response is None:
                continue
            try:
                root = ElementTree.fromstring(response.content)
            except ElementTree.ParseError:
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
    suffix = path[len(prefix.rstrip("/")) :].strip("/")
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
    for selector in (".cn-entry-name", ".fn", "main h1", "article h1", "h1", "main h2", "article h2"):
        for element in soup.select(selector):
            value = element.get_text(" ", strip=True)
            if value:
                return value
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = re.sub(r"\s*[-–|]\s*Member of Lewes Chamber.*$", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s*[-–|].*$", "", title).strip()


def _lines(soup: BeautifulSoup) -> list[str]:
    return [re.sub(r"\s+", " ", text).strip() for text in soup.stripped_strings if text.strip()]


def _sector_text(soup: BeautifulSoup) -> str:
    lines = _lines(soup)
    for index, line in enumerate(lines):
        if line.casefold().rstrip(":") == "sector":
            values: list[str] = []
            for candidate in lines[index + 1 : index + 5]:
                if _looks_like_contact_or_heading(candidate):
                    break
                values.append(candidate)
            return " ".join(values)
    return ""


def _address_text(soup: BeautifulSoup) -> str:
    lines = _lines(soup)
    for index, line in enumerate(lines):
        if line.casefold().rstrip(":") == "address":
            values: list[str] = []
            for candidate in lines[index + 1 : index + 9]:
                if candidate.casefold().rstrip(":") == "sector" or _looks_like_contact_or_heading(candidate):
                    break
                values.append(candidate)
            return _clean_address(", ".join(values))
    return ""


def _external_website(soup: BeautifulSoup, source_url: str) -> str:
    source_host = urlparse(source_url).netloc.casefold()
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True).casefold()
        if "website" not in text and "web site" not in text:
            continue
        href = urljoin(source_url, str(anchor.get("href") or "").strip())
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        host = parsed.netloc.casefold()
        if host == source_host or any(domain in host for domain in ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com")):
            continue
        return href.rstrip("/")
    return ""


def _description(soup: BeautifulSoup, name: str) -> str:
    for container in (soup.select_one("main"), soup.select_one("article"), soup):
        if not container:
            continue
        for paragraph in container.find_all("p"):
            text = paragraph.get_text(" ", strip=True)
            if len(text) >= 40 and "unsolicited mass" not in text.casefold() and name.casefold() != text.casefold():
                return text[:1200]
    return "Current member of Lewes Chamber of Commerce; sector information is published on the Chamber member page."


def _looks_like_contact_or_heading(value: str) -> bool:
    lower = value.casefold().strip()
    return (
        lower in {
            "image",
            "website",
            "facebook",
            "instagram",
            "linkedin",
            "twitter",
            "back to the business directory index",
        }
        or "@" in value
        or bool(re.fullmatch(r"[+\d][\d\s().-]{7,}", value))
    )


def _clean_address(value: str) -> str:
    parts = [part.strip(" ,") for part in re.split(r"\s*,\s*", value) if part.strip(" ,")]
    if parts and parts[-1].casefold() == "united kingdom":
        parts.pop()
    return ", ".join(parts)
