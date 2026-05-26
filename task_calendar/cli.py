"""Интерфейс командной строки для приложения задач."""

from __future__ import annotations

import argparse
from datetime import date, time
from typing import Sequence

from .config import database_url_from_env
from .models import Task
from .storage import TaskRepository


def main(argv: Sequence[str] | None = None) -> int:
    """Разбирает аргументы командной строки и выполняет выбранную команду."""
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
        description="Управление личными задачами из терминала.",
    )
    parser.add_argument(
        "--database-url",
        default=database_url_from_env(),
        help="URL подключения к PostgreSQL.",
    )

    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Создать новую задачу.")
    add_parser.add_argument("title", help="Название задачи.")
    add_parser.add_argument(
        "--description",
        default="",
        help="Необязательное описание задачи.",
    )
    add_parser.add_argument(
        "--due-date",
        type=_parse_date,
        help="Необязательная дата в формате ГГГГ-ММ-ДД.",
    )
    add_parser.add_argument(
        "--start-time",
        type=_parse_time,
        help="Необязательное время начала в формате ЧЧ:ММ.",
    )
    add_parser.add_argument(
        "--end-time",
        type=_parse_time,
        help="Необязательное время окончания в формате ЧЧ:ММ.",
    )

    list_parser = subparsers.add_parser("list", help="Показать задачи.")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Показывать и выполненные задачи.",
    )

    complete_parser = subparsers.add_parser("complete", help="Пометить задачу как выполненную.")
    complete_parser.add_argument("task_id", type=int, help="Идентификатор задачи.")

    delete_parser = subparsers.add_parser("delete", help="Удалить задачу.")
    delete_parser.add_argument("task_id", type=int, help="Идентификатор задачи.")

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

    print(f"Создана задача #{task.id}: {task.title}")
    return 0


def _list_tasks(repository: TaskRepository, args: argparse.Namespace) -> int:
    tasks = repository.list_tasks(include_completed=args.all)
    if not tasks:
        print("Задачи не найдены.")
        return 0

    print("ID  Статус  Дата        Время        Название")
    for task in tasks:
        print(_format_task(task))
    return 0


def _complete_task(repository: TaskRepository, args: argparse.Namespace) -> int:
    if repository.complete_task(args.task_id):
        print(f"Задача #{args.task_id} отмечена как выполненная")
        return 0

    print(f"Задача #{args.task_id} не найдена.")
    return 1


def _delete_task(repository: TaskRepository, args: argparse.Namespace) -> int:
    if repository.delete_task(args.task_id):
        print(f"Задача #{args.task_id} удалена")
        return 0

    print(f"Задача #{args.task_id} не найдена.")
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
            "Дата должна быть в формате ГГГГ-ММ-ДД."
        ) from error


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Время должно быть в формате ЧЧ:ММ."
        ) from error


def _format_time_range(start_time: time | None, end_time: time | None) -> str:
    if start_time is None and end_time is None:
        return "-"
    if start_time is not None and end_time is not None:
        return f"{start_time:%H:%M}-{end_time:%H:%M}"
    if start_time is not None:
        return f"с {start_time:%H:%M}"
    return f"до {end_time:%H:%M}"


if __name__ == "__main__":
    raise SystemExit(main())
