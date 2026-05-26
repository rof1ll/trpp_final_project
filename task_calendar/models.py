"""Domain models used by the task manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True)
class Task:
    """A single user task stored by the application."""

    id: int
    title: str
    description: str
    due_date: date | None
    start_time: time | None
    end_time: time | None
    is_completed: bool
    created_at: datetime
    completed_at: datetime | None = None
