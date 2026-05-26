"""Command-line interface for the task manager."""

from __future__ import annotations

import argparse
from datetime import date, time
from typing import Sequence

from .config import database_url_from_env
from .models import Task
from .storage import TaskRepository


def main(argv: Sequence[str] | None = None) -> int:
    """Parse command-line arguments and execute the selected command."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    repository = TaskRepository(args.database_url)
    try:
        repository.initialize()
    except RuntimeError as error:
        print(error)
        return 1

    if args.command == "add":
        return _add_task(repository, args)
    if args.command == "list":
        return _list_tasks(repository, args)
    if args.command == "complete":
        return _complete_task(repository, args)
    if args.command == "delete":
        return _delete_task(repository, args)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todo-app",
        description="Manage personal tasks from the terminal.",
    )
    parser.add_argument(
        "--database-url",
        default=database_url_from_env(),
        help="PostgreSQL connection URL.",
    )

    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Create a new task.")
    add_parser.add_argument("title", help="Task title.")
    add_parser.add_argument(
        "--description",
        default="",
        help="Optional task description.",
    )
    add_parser.add_argument(
        "--due-date",
        type=_parse_date,
        help="Optional due date in YYYY-MM-DD format.",
    )
    add_parser.add_argument(
        "--start-time",
        type=_parse_time,
        help="Optional start time in HH:MM format.",
    )
    add_parser.add_argument(
        "--end-time",
        type=_parse_time,
        help="Optional end time in HH:MM format.",
    )

    list_parser = subparsers.add_parser("list", help="Show tasks.")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Show completed tasks too.",
    )

    complete_parser = subparsers.add_parser("complete", help="Mark a task as done.")
    complete_parser.add_argument("task_id", type=int, help="Task identifier.")

    delete_parser = subparsers.add_parser("delete", help="Delete a task.")
    delete_parser.add_argument("task_id", type=int, help="Task identifier.")

    return parser


def _add_task(repository: TaskRepository, args: argparse.Namespace) -> int:
    try:
        task = repository.add_task(
            title=args.title,
            description=args.description,
            due_date=args.due_date,
            start_time=args.start_time,
            end_time=args.end_time,
        )
    except ValueError as error:
        print(error)
        return 1

    print(f"Created task #{task.id}: {task.title}")
    return 0


def _list_tasks(repository: TaskRepository, args: argparse.Namespace) -> int:
    tasks = repository.list_tasks(include_completed=args.all)
    if not tasks:
        print("No tasks found.")
        return 0

    print("ID  Status  Due date    Time         Title")
    for task in tasks:
        print(_format_task(task))
    return 0


def _complete_task(repository: TaskRepository, args: argparse.Namespace) -> int:
    if repository.complete_task(args.task_id):
        print(f"Completed task #{args.task_id}")
        return 0

    print(f"Task #{args.task_id} was not found.")
    return 1


def _delete_task(repository: TaskRepository, args: argparse.Namespace) -> int:
    if repository.delete_task(args.task_id):
        print(f"Deleted task #{args.task_id}")
        return 0

    print(f"Task #{args.task_id} was not found.")
    return 1


def _format_task(task: Task) -> str:
    status = "[x]" if task.is_completed else "[ ]"
    due_date = task.due_date.isoformat() if task.due_date else "-"
    time_range = _format_time_range(task.start_time, task.end_time)
    return f"{task.id:<3} {status:<6} {due_date:<10}  {time_range:<11}  {task.title}"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Date must use YYYY-MM-DD format."
        ) from error


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Time must use HH:MM format."
        ) from error


def _format_time_range(start_time: time | None, end_time: time | None) -> str:
    if start_time is None and end_time is None:
        return "-"
    if start_time is not None and end_time is not None:
        return f"{start_time:%H:%M}-{end_time:%H:%M}"
    if start_time is not None:
        return f"from {start_time:%H:%M}"
    return f"until {end_time:%H:%M}"


if __name__ == "__main__":
    raise SystemExit(main())
