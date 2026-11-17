FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY packages/shared-python /src/packages/shared-python
COPY apps/api /app

RUN pip install --no-cache-dir /src/packages/shared-python /app

RUN useradd --create-home --uid 10001 orgweave
USER 10001

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
