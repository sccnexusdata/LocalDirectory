from __future__ import annotations

from pathlib import Path

from localdirectory.exporters.site_bundle import export_site_bundle
from localdirectory.models import ListingRecord


def export_leweslive(records: list[ListingRecord], output_dir: Path) -> Path:
    """Backward-compatible LewesLive adapter.

    New locality configurations should use ``export_site_bundle`` through the
    runner's ``outputs.site_bundle`` configuration.  This wrapper remains only
    so older callers/tests do not require an abrupt migration.
    """
    return export_site_bundle(
        records,
        output_dir,
        site_slug="leweslive",
        js_global="LEWESLIVE_DIRECTORY",
    )
