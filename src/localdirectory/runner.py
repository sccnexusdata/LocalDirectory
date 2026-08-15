from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from localdirectory.config import DirectoryConfig
from localdirectory.coverage import build_coverage_report
from localdirectory.entity_resolution import merge_records
from localdirectory.exporters import export_leweslive, export_public, write_csv, write_geojson, write_json
from localdirectory.models import ListingRecord, utc_now_iso
from localdirectory.plugins import CompaniesHousePlugin, FHRSPlugin, JSONLDPlugin, ManualCSVPlugin, OSMOverpassPlugin
from localdirectory.plugins.base import HarvestResult
from localdirectory.validation import validate_records


class DirectoryRunner:
    def __init__(self, config: DirectoryConfig, offline: bool = False):
        self.config = config
        self.offline = offline
        self.timeout = int(os.getenv("LOCALDIRECTORY_TIMEOUT_SECONDS", "30"))
        self.user_agent = os.getenv(
            "LOCALDIRECTORY_USER_AGENT",
            "LocalDirectory/0.1 (+https://github.com/sccnexusdata/LocalDirectory)",
        )

    def run(self) -> Path:
        output_dir = self.config.outputs_dir / self.config.slug
        output_dir.mkdir(parents=True, exist_ok=True)

        results: list[HarvestResult] = []
        all_records: list[ListingRecord] = []
        for plugin in self._plugins():
            result = self._harvest(plugin)
            results.append(result)
            all_records.extend(result.records)

        if not self.offline and self._source_enabled("json_ld"):
            json_ld_urls = self._json_ld_urls(all_records)
            json_ld_timeout = int(self.config.source_config.get("json_ld_timeout_seconds", min(self.timeout, 15)))
            result = self._harvest(JSONLDPlugin(json_ld_urls, json_ld_timeout, self.user_agent))
            if json_ld_urls:
                result.message = f"Queued {len(json_ld_urls)} discovered/configured websites. {result.message}"
            else:
                result.message = "No eligible discovered/configured websites were available for JSON-LD enrichment"
            results.append(result)
            all_records.extend(result.records)

        merged = merge_records(all_records)
        summary = validate_records(merged, self.config.location, self.config.policy)
        merged.sort(key=lambda r: (r.primary_category, r.name.casefold()))

        coverage = build_coverage_report(merged, dict(self.config.policy.get("coverage", {})))

        write_json(merged, output_dir / "listings.json")
        write_csv(merged, output_dir / "listings.csv")
        write_geojson(merged, output_dir / "listings.geojson")
        export_public(merged, output_dir, self.config.project_name)
        export_leweslive(merged, output_dir)
        (output_dir / "coverage-report.json").write_text(
            json.dumps({"generated_at": utc_now_iso(), **coverage}, indent=2), encoding="utf-8"
        )

        source_health = {
            "generated_at": utc_now_iso(),
            "offline": self.offline,
            "sources": [
                {
                    "source": result.source_name,
                    "ok": result.ok,
                    "message": result.message,
                    "records": len(result.records),
                    "requests_made": result.requests_made,
                }
                for result in results
            ],
        }
        (output_dir / "source-health.json").write_text(json.dumps(source_health, indent=2), encoding="utf-8")

        provenance = []
        for record in merged:
            for source in record.sources:
                provenance.append({
                    "listing_id": record.listing_id,
                    "listing_name": record.name,
                    "source_name": source.source_name,
                    "source_type": source.source_type,
                    "source_class": source.source_class,
                    "source_id": source.source_id,
                    "source_url": source.source_url,
                    "retrieved_at": source.retrieved_at,
                })
        (output_dir / "source-provenance.json").write_text(
            json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        review_queue = [record.to_dict() for record in merged if record.review_required]
        (output_dir / "review-queue.json").write_text(
            json.dumps(review_queue, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        report = {
            "generated_at": utc_now_iso(),
            "project": self.config.project_name,
            "location": self.config.location,
            "summary": asdict(summary),
            "source_record_counts": {r.source_name: len(r.records) for r in results},
            "source_failures": [r.source_name for r in results if not r.ok],
            "quality_flags": _flag_counts(merged),
            "coverage": coverage,
        }
        (output_dir / "quality-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return output_dir

    def _harvest(self, plugin) -> HarvestResult:
        try:
            return plugin.harvest()
        except Exception as exc:
            return HarvestResult(
                getattr(plugin, "name", plugin.__class__.__name__),
                ok=False,
                message=f"{exc.__class__.__name__}: {exc}",
            )

    def _source_enabled(self, source_name: str) -> bool:
        enabled = set(self.config.source_config.get("enabled", ["fhrs", "osm_overpass", "companies_house", "json_ld"]))
        return source_name in enabled

    def _json_ld_urls(self, records: list[ListingRecord]) -> list[str]:
        sources = self.config.source_config
        candidates = [*list(sources.get("websites", [])), *(record.website for record in records if record.website)]
        maximum = max(0, int(sources.get("json_ld_max_websites", 60)))
        seen: set[str] = set()
        urls: list[str] = []
        for candidate in candidates:
            value = str(candidate or "").strip()
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            normalised = value.rstrip("/")
            key = normalised.casefold()
            if key in seen:
                continue
            seen.add(key)
            urls.append(normalised)
            if len(urls) >= maximum:
                break
        return urls

    def _plugins(self):
        location = self.config.location
        sources = self.config.source_config
        plugins = []
        manual_path = sources.get("manual_csv", "data/manual/listings.csv")
        plugins.append(ManualCSVPlugin(manual_path))
        if self.offline:
            return plugins

        enabled = set(sources.get("enabled", ["fhrs", "osm_overpass", "companies_house", "json_ld"]))
        if "fhrs" in enabled:
            plugins.append(
                FHRSPlugin(
                    float(location["latitude"]),
                    float(location["longitude"]),
                    float(location.get("radius_miles", 10)),
                    self.timeout,
                    self.user_agent,
                )
            )
        if "osm_overpass" in enabled:
            plugins.append(
                OSMOverpassPlugin(
                    float(location["latitude"]),
                    float(location["longitude"]),
                    float(location.get("radius_km") or float(location.get("radius_miles", 10)) * 1.609344),
                    endpoint=str(sources.get("overpass_endpoint", "https://overpass-api.de/api/interpreter")),
                    timeout=max(self.timeout, 45),
                    user_agent=self.user_agent,
                )
            )
        if "companies_house" in enabled:
            plugins.append(
                CompaniesHousePlugin(
                    str(location.get("name", "")),
                    timeout=self.timeout,
                    user_agent=self.user_agent,
                    max_results=int(sources.get("companies_house_max_results", 500)),
                )
            )
        return plugins


def _flag_counts(records: list[ListingRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for flag in record.quality_flags:
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items()))
