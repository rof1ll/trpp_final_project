# Календарь задач

Desktop-приложение на Python для управления задачами в формате календаря. Проект использует `PySide6` для графического интерфейса и `PostgreSQL` для хранения задач.

## Зависимости

- `PySide6>=6.7`
- `psycopg[binary]>=3.2`
- `Sphinx>=8.0`

## Настройка PostgreSQL

Локальную базу можно поднять через Docker:

```bash
docker compose up -d postgres
```

Строка подключения по умолчанию:

```text
postgresql://task_calendar:task_calendar@localhost:5432/task_calendar
```

Если нужна своя база, задайте переменную окружения:

```powershell
$env:TASK_CALENDAR_DATABASE_URL="postgresql://user:password@localhost:5432/task_calendar"
```

## Установка

Установка зависимостей:

```bash
python -m pip install -r requirements.txt
```

Установка самого проекта в editable-режиме:

```bash
python -m pip install -e . --no-build-isolation
```

## Запуск приложения

Запуск графического приложения:

```bash
python -m task_calendar
```

После установки пакета также доступны команды:

```bash
task-calendar
task-calendar-cli --help
task-calendar-cli list --all
```

## Проверка CLI

Пример добавления и просмотра тестовой задачи:

```bash
task-calendar-cli add "Тестовая задача" --due-date 2026-06-01 --start-time 09:00 --end-time 10:00
task-calendar-cli list --all
task-calendar-cli complete 1
task-calendar-cli delete 1
```

## Сборка пакета

Проект использует `setuptools`. Для сборки wheel и sdist:

```bash
python -m pip install build
python -m build
```

## Сборка `.exe`

Для сборки Windows-исполняемого файла используется `PyInstaller`.

Установка:

```bash
python -m pip install .[exe] --no-build-isolation
```

Сборка GUI-приложения:

```bash
pyinstaller task_calendar.spec
```

Готовый файл появится по пути:

```text
dist/task_calendar.exe
```

## Документация

HTML-документация собирается через Sphinx:

```bash
python -m sphinx -b html docs docs/_build/html
```

Стартовая страница будет создана по пути `docs/_build/html/index.html`.

## Docker

Для третьей части проекта приложение упаковано в Docker-образ. В контейнере используется CLI-режим, который подключается к PostgreSQL через переменную окружения `TASK_CALENDAR_DATABASE_URL`.

Запуск контейнера приложения и PostgreSQL:

```bash
docker compose up --build
```

Примеры CLI-команд в контейнере:

```bash
docker compose run --rm app python -m task_calendar.cli list --all
docker compose run --rm app python -m task_calendar.cli add "Подготовить отчет" --due-date 2026-06-01
```
