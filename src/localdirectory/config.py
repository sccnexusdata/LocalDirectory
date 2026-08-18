from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class DirectoryConfig:
    path: Path
    raw: dict[str, Any]

    @property
    def project_name(self) -> str:
        return str(self.raw.get("project", {}).get("name", "LocalDirectory"))

    @property
    def slug(self) -> str:
        return str(self.raw.get("project", {}).get("slug", "localdirectory"))

    @property
    def location(self) -> dict[str, Any]:
        return dict(self.raw.get("location", {}))

    @property
    def source_config(self) -> dict[str, Any]:
        return dict(self.raw.get("sources", {}))

    @property
    def policy(self) -> dict[str, Any]:
        return dict(self.raw.get("policy", {}))

    @property
    def outputs(self) -> dict[str, Any]:
        return dict(self.raw.get("outputs", {}))

    @property
    def outputs_dir(self) -> Path:
        return Path(self.outputs.get("directory", "exports"))

    @property
    def site_bundle(self) -> dict[str, str] | None:
        raw = self.outputs.get("site_bundle")
        if not raw:
            return None
        if not isinstance(raw, dict):
            raise TypeError("outputs.site_bundle must be a mapping")
        slug = str(raw.get("slug", "")).strip()
        js_global = str(raw.get("js_global", "")).strip()
        if not slug or not js_global:
            raise ValueError("outputs.site_bundle requires both slug and js_global")
        return {"slug": slug, "js_global": js_global}


def load_config(path: str | Path) -> DirectoryConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return DirectoryConfig(path=config_path, raw=raw)
