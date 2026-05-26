from __future__ import annotations

import importlib.util
import os
import unittest
from datetime import date, datetime, time, timezone

from cmd.storage import TaskRepository, _row_to_task

TEST_DATABASE_URL = os.environ.get("TASK_CALENDAR_TEST_DATABASE_URL")
HAS_PSYCOPG = importlib.util.find_spec("psycopg") is not None


class TaskRepositoryValidationTest(unittest.TestCase):
    def test_add_task_requires_non_empty_title_before_database_connection(self) -> None:
        repository = TaskRepository("postgresql://example/example")

        with self.assertRaises(ValueError):
            repository.add_task("   ")

    def test_row_to_task_maps_postgres_values(self) -> None:
        created_at = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)

        task = _row_to_task(
            {
                "id": 7,
                "title": "Plan the day",
                "description": "Choose tasks for the morning",
                "due_date": date(2026, 5, 26),
                "start_time": time(9, 0),
                "end_time": time(10, 30),
                "is_completed": False,
                "created_at": created_at,
                "completed_at": None,
            }
        )

        self.assertEqual(7, task.id)
        self.assertEqual("Plan the day", task.title)
        self.assertEqual(date(2026, 5, 26), task.due_date)
        self.assertEqual(time(9, 0), task.start_time)
        self.assertEqual(time(10, 30), task.end_time)
        self.assertFalse(task.is_completed)
        self.assertEqual(created_at, task.created_at)

    def test_add_task_rejects_invalid_time_range_before_database_connection(self) -> None:
        repository = TaskRepository("postgresql://example/example")

        with self.assertRaises(ValueError):
            repository.add_task(
                "Invalid time",
                start_time=time(12, 0),
                end_time=time(11, 0),
            )

    def test_update_task_requires_non_empty_title_before_database_connection(self) -> None:
        repository = TaskRepository("postgresql://example/example")

        with self.assertRaises(ValueError):
            repository.update_task(
                1,
                "   ",
                "",
                date(2026, 5, 26),
                time(9, 0),
                time(10, 0),
            )


@unittest.skipUnless(
    TEST_DATABASE_URL and HAS_PSYCOPG,
    "PostgreSQL integration tests require TASK_CALENDAR_TEST_DATABASE_URL and psycopg.",
)
class TaskRepositoryPostgresTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TaskRepository(TEST_DATABASE_URL or "")
        self.repository.initialize()
        with self.repository._connect() as connection:
            connection.execute("TRUNCATE TABLE tasks RESTART IDENTITY")

    def test_add_and_list_task_for_date(self) -> None:
        task = self.repository.add_task(
            title="Write report",
            description="Prepare the first project part",
            due_date=date(2026, 6, 1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        tasks = self.repository.list_tasks_for_date(date(2026, 6, 1))

        self.assertEqual(task.id, tasks[0].id)
        self.assertEqual("Write report", tasks[0].title)
        self.assertEqual(date(2026, 6, 1), tasks[0].due_date)
        self.assertEqual(time(9, 0), tasks[0].start_time)
        self.assertEqual(time(10, 0), tasks[0].end_time)
        self.assertFalse(tasks[0].is_completed)

    def test_complete_task_hides_it_from_active_count(self) -> None:
        task = self.repository.add_task("Read assignment", due_date=date(2026, 6, 1))

        was_completed = self.repository.complete_task(task.id)

        self.assertTrue(was_completed)
        self.assertEqual(
            {},
            self.repository.count_active_tasks_by_date(
                date(2026, 6, 1),
                date(2026, 6, 1),
            ),
        )
        self.assertTrue(
            self.repository.list_tasks_for_date(date(2026, 6, 1))[0].is_completed
        )

    def test_delete_task_removes_it(self) -> None:
        task = self.repository.add_task("Temporary task", due_date=date(2026, 6, 2))

        was_deleted = self.repository.delete_task(task.id)

        self.assertTrue(was_deleted)
        self.assertEqual([], self.repository.list_tasks_for_date(date(2026, 6, 2)))

    def test_missing_task_operations_report_false(self) -> None:
        self.assertFalse(self.repository.complete_task(999))
        self.assertFalse(self.repository.delete_task(999))

    def test_update_task_schedule_moves_task(self) -> None:
        task = self.repository.add_task("Move me", due_date=date(2026, 6, 1))

        was_updated = self.repository.update_task_schedule(
            task.id,
            date(2026, 6, 2),
            time(14, 0),
            time(15, 30),
        )

        moved_task = self.repository.get_task(task.id)
        self.assertTrue(was_updated)
        self.assertIsNotNone(moved_task)
        self.assertEqual(date(2026, 6, 2), moved_task.due_date)
        self.assertEqual(time(14, 0), moved_task.start_time)
        self.assertEqual(time(15, 30), moved_task.end_time)

    def test_update_task_changes_editable_fields(self) -> None:
        task = self.repository.add_task("Original", due_date=date(2026, 6, 1))

        was_updated = self.repository.update_task(
            task.id,
            "Updated",
            "New description",
            date(2026, 6, 3),
            time(16, 0),
            time(17, 0),
        )

        updated_task = self.repository.get_task(task.id)
        self.assertTrue(was_updated)
        self.assertIsNotNone(updated_task)
        self.assertEqual("Updated", updated_task.title)
        self.assertEqual("New description", updated_task.description)
        self.assertEqual(date(2026, 6, 3), updated_task.due_date)
        self.assertEqual(time(16, 0), updated_task.start_time)
        self.assertEqual(time(17, 0), updated_task.end_time)


if __name__ == "__main__":
    unittest.main()
