from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class TocEntry:
    title: str
    url: str
    arc: str
    phase: Optional[str]
    chapter: str
    order: int

    @property
    def identity_key(self) -> str:
        phase = self.phase or ""
        return f"{self.url}|{self.arc}|{phase}|{self.chapter}"


@dataclass(slots=True)
class SyncSummary:
    total: int = 0
    new: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
