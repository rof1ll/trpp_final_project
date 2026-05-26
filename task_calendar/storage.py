"""PostgreSQL storage for tasks."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from typing import Any, Iterator, Mapping

from .models import Task


class TaskRepository:
    """Persist and load tasks from PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def initialize(self) -> None:
        """Create the database schema when it does not exist yet."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    due_date DATE,
                    start_time TIME,
                    end_time TIME,
                    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ
                )
                """
            )
            connection.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS start_time TIME")
            connection.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS end_time TIME")

    def add_task(
        self,
        title: str,
        description: str = "",
        due_date: date | None = None,
        start_time: time | None = None,
        end_time: time | None = None,
    ) -> Task:
        """Create a task and return its stored representation."""
        title = title.strip()
        if not title:
            raise ValueError("Task title is required.")
        _validate_time_range(start_time, end_time)

        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO tasks (
                    title,
                    description,
                    due_date,
                    start_time,
                    end_time,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (title, description, due_date, start_time, end_time, created_at),
            ).fetchone()

        if row is None:
            raise RuntimeError("Task was not stored correctly.")
        return _row_to_task(row)

    def get_task(self, task_id: int) -> Task | None:
        """Return one task by id, or None when it does not exist."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = %s",
                (task_id,),
            ).fetchone()
        return _row_to_task(row) if row is not None else None

    def list_tasks(self, include_completed: bool = False) -> list[Task]:
        """Return tasks ordered by completion state, due date, and id."""
        query = "SELECT * FROM tasks"
        parameters: list[object] = []
        if not include_completed:
            query += " WHERE is_completed = FALSE"
        query += " ORDER BY is_completed ASC, due_date ASC NULLS LAST, start_time ASC NULLS LAST, id ASC"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_task(row) for row in rows]

    def list_tasks_for_date(
        self,
        target_date: date,
        include_completed: bool = True,
    ) -> list[Task]:
        """Return tasks planned for a specific date."""
        query = "SELECT * FROM tasks WHERE due_date = %s"
        parameters: list[object] = [target_date]
        if not include_completed:
            query += " AND is_completed = FALSE"
        query += " ORDER BY is_completed ASC, start_time ASC NULLS LAST, id ASC"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_task(row) for row in rows]

    def count_active_tasks_by_date(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[date, int]:
        """Return active task counts grouped by date for a date range."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT due_date, COUNT(*) AS task_count
                FROM tasks
                WHERE is_completed = FALSE
                  AND due_date BETWEEN %s AND %s
                GROUP BY due_date
                """,
                (start_date, end_date),
            ).fetchall()

        counts: dict[date, int] = {}
        for row in rows:
            task_date = _value_to_date(row["due_date"])
            if task_date is not None:
                counts[task_date] = int(row["task_count"])
        return counts

    def count_tasks_by_date(
        self,
        start_date: date,
        end_date: date,
        include_completed: bool = True,
    ) -> dict[date, int]:
        """Return task counts grouped by date for a date range."""
        query = """
            SELECT due_date, COUNT(*) AS task_count
            FROM tasks
            WHERE due_date BETWEEN %s AND %s
        """
        parameters: list[object] = [start_date, end_date]
        if not include_completed:
            query += " AND is_completed = FALSE"
        query += " GROUP BY due_date"

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()

        counts: dict[date, int] = {}
        for row in rows:
            task_date = _value_to_date(row["due_date"])
            if task_date is not None:
                counts[task_date] = int(row["task_count"])
        return counts

    def update_task_schedule(
        self,
        task_id: int,
        due_date: date | None,
        start_time: time | None,
        end_time: time | None,
    ) -> bool:
        """Move a task to another date and time range."""
        _validate_time_range(start_time, end_time)
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE tasks
                SET due_date = %s, start_time = %s, end_time = %s
                WHERE id = %s
                RETURNING id
                """,
                (due_date, start_time, end_time, task_id),
            ).fetchone()
        return row is not None

    def update_task(
        self,
        task_id: int,
        title: str,
        description: str,
        due_date: date | None,
        start_time: time | None,
        end_time: time | None,
    ) -> bool:
        """Update editable task fields."""
        title = title.strip()
        if not title:
            raise ValueError("Task title is required.")
        _validate_time_range(start_time, end_time)
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE tasks
                SET title = %s,
                    description = %s,
                    due_date = %s,
                    start_time = %s,
                    end_time = %s
                WHERE id = %s
                RETURNING id
                """,
                (title, description, due_date, start_time, end_time, task_id),
            ).fetchone()
        return row is not None

    def complete_task(self, task_id: int) -> bool:
        """Mark a task as completed and report whether it existed."""
        completed_at = datetime.now(timezone.utc).replace(microsecond=0)
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE tasks
                SET is_completed = TRUE, completed_at = %s
                WHERE id = %s
                RETURNING id
                """,
                (completed_at, task_id),
            ).fetchone()
        return row is not None

    def delete_task(self, task_id: int) -> bool:
        """Delete a task and report whether it existed."""
        with self._connect() as connection:
            row = connection.execute(
                "DELETE FROM tasks WHERE id = %s RETURNING id",
                (task_id,),
            ).fetchone()
        return row is not None

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        psycopg, dict_row = _load_psycopg()
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection


def _load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError(
            "PostgreSQL driver is not installed. Run "
            "`python -m pip install -r requirements.txt`."
        ) from error
    return psycopg, dict_row


def _row_to_task(row: Mapping[str, object]) -> Task:
    return Task(
        id=int(row["id"]),
        title=str(row["title"]),
        description=str(row["description"]),
        due_date=_value_to_date(row["due_date"]),
        start_time=_value_to_time(row.get("start_time")),
        end_time=_value_to_time(row.get("end_time")),
        is_completed=bool(row["is_completed"]),
        created_at=_value_to_datetime(row["created_at"]),
        completed_at=_value_to_datetime(row["completed_at"]),
    )


def _value_to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Unsupported date value: {value!r}")


def _value_to_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _value_to_time(value: object) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return time.fromisoformat(value)
    raise TypeError(f"Unsupported time value: {value!r}")


def _validate_time_range(start_time: time | None, end_time: time | None) -> None:
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise ValueError("Task end time must be after start time.")
