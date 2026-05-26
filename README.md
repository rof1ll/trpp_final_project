# Календарь задач

Desktop-приложение на Python для управления задачами в формате календаря. Пользователь выбирает дату в компактном календаре слева, работает с задачей в прокручиваемой панели, видит расписание на основном экране, переносит задачи мышью по дате и времени и запускает круговой таймер для выбранной задачи.

## Настройка PostgreSQL

Локальную базу можно поднять через Docker:

```bash
docker compose up -d
```

Строка подключения по умолчанию:

```text
postgresql://task_calendar:task_calendar@localhost:5432/task_calendar
```

При необходимости можно указать свою базу в PowerShell:

```powershell
$env:TASK_CALENDAR_DATABASE_URL="postgresql://user:password@localhost:5432/task_calendar"
```

## Быстрый запуск

Установка зависимостей:

```bash
python -m pip install -r requirements.txt
```

Локальную базу можно поднять через Docker:

```bash
docker compose up -d
```

Запуск desktop-приложения:

```bash
python -m todo_app
```
