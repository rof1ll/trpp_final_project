"""Предметные модели, используемые приложением задач."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True)
class Task:
    """Одна пользовательская задача, сохраненная приложением."""

    id: int
    title: str
    description: str
    due_date: date | None
    start_time: time | None
    end_time: time | None
    is_completed: bool
    created_at: datetime
    completed_at: datetime | None = None
