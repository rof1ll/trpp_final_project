FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY task_calendar ./task_calendar

RUN python -m pip install --upgrade pip && \
    python -m pip install .

CMD ["python", "-m", "task_calendar.cli", "list", "--all"]
