"""Modèles de domaine simples, indépendants de Tkinter et de SQLite."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class CareRecommendation:
    interval_days: int
    next_check: date | None
    confidence: float
    explanation: list[str] = field(default_factory=list)

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.8:
            return "élevée"
        if self.confidence >= 0.55:
            return "moyenne"
        return "faible"


@dataclass(slots=True)
class TimelineItem:
    item_id: str
    plant_id: str
    kind: str
    event_date: str
    title: str
    details: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
