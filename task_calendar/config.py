"""Вспомогательные функции конфигурации приложения."""

from __future__ import annotations

import os

DEFAULT_DATABASE_URL = "postgresql://task_calendar:task_calendar@localhost:5432/task_calendar"
DATABASE_URL_ENV = "TASK_CALENDAR_DATABASE_URL"


def database_url_from_env() -> str:
    """Возвращает URL базы данных из окружения или значение по умолчанию."""
    return os.environ.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)
