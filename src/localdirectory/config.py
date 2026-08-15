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
    def outputs_dir(self) -> Path:
        return Path(self.raw.get("outputs", {}).get("directory", "exports"))


def load_config(path: str | Path) -> DirectoryConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return DirectoryConfig(path=config_path, raw=raw)
