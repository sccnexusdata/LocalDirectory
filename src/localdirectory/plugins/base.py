from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from localdirectory.models import ListingRecord


@dataclass(slots=True)
class HarvestResult:
    source_name: str
    records: list[ListingRecord] = field(default_factory=list)
    ok: bool = True
    message: str = ""
    requests_made: int = 0


class Plugin(Protocol):
    name: str

    def harvest(self) -> HarvestResult: ...
