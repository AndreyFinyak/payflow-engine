FROM python:3.14-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install uv --quiet

COPY pyproject.toml uv.lock ./

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN uv sync --locked --no-dev


EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]