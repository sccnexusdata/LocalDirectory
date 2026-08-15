from __future__ import annotations

from collections.abc import Iterable

import requests

from localdirectory.models import ListingRecord
from localdirectory.text import normalise_postcode


DEFAULT_ENDPOINT = "https://api.postcodes.io/postcodes"


def _chunks(values: list[str], size: int = 100) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def enrich_missing_coordinates(
    records: list[ListingRecord],
    *,
    timeout: int = 20,
    user_agent: str = "LocalDirectory/0.1",
    endpoint: str = DEFAULT_ENDPOINT,
) -> dict:
    needed = sorted({
        normalise_postcode(record.postcode)
        for record in records
        if record.postcode and (record.latitude is None or record.longitude is None)
    })
    if not needed:
        return {
            "ok": True,
            "postcodes_requested": 0,
            "postcodes_resolved": 0,
            "records_enriched": 0,
            "requests_made": 0,
            "message": "No missing postcode coordinates required enrichment",
        }

    resolved: dict[str, tuple[float, float]] = {}
    requests_made = 0
    failures: list[str] = []
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": user_agent}

    for batch in _chunks(needed, 100):
        try:
            response = requests.post(endpoint, json={"postcodes": batch}, headers=headers, timeout=timeout)
            requests_made += 1
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("result", []) if isinstance(payload, dict) else []:
                query = normalise_postcode(str((item or {}).get("query") or ""))
                result = (item or {}).get("result") or {}
                try:
                    latitude = float(result.get("latitude"))
                    longitude = float(result.get("longitude"))
                except (TypeError, ValueError):
                    continue
                if query:
                    resolved[query] = (latitude, longitude)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{exc.__class__.__name__}: {exc}")

    enriched = 0
    for record in records:
        postcode = normalise_postcode(record.postcode)
        coordinates = resolved.get(postcode)
        if not coordinates:
            continue
        changed = False
        if record.latitude is None:
            record.latitude = coordinates[0]
            record.field_provenance.setdefault("latitude", []).append("Postcodes.io postcode centroid")
            changed = True
        if record.longitude is None:
            record.longitude = coordinates[1]
            record.field_provenance.setdefault("longitude", []).append("Postcodes.io postcode centroid")
            changed = True
        if changed:
            enriched += 1

    ok = not failures or bool(resolved)
    message = f"Resolved {len(resolved)}/{len(needed)} postcodes; enriched {enriched} records"
    if failures:
        message += f"; {len(failures)} batch failure(s)"
    return {
        "ok": ok,
        "postcodes_requested": len(needed),
        "postcodes_resolved": len(resolved),
        "records_enriched": enriched,
        "requests_made": requests_made,
        "message": message,
    }
