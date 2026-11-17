FROM python:3.13-slim

ARG WORKER_PATH
ARG WORKER_MODULE
ARG WORKER_NAME

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    WORKER_NAME=${WORKER_NAME} \
    WORKER_MODULE=${WORKER_MODULE}

WORKDIR /app

COPY packages/shared-python /src/packages/shared-python
COPY packages/agent-sdk /src/packages/agent-sdk
COPY packages/skill-sdk /src/packages/skill-sdk
COPY apps/api /src/apps/api
COPY ${WORKER_PATH} /app/worker

RUN pip install --no-cache-dir \
        /src/packages/shared-python \
        /src/packages/agent-sdk \
        /src/packages/skill-sdk \
        /src/apps/api \
        /app/worker

RUN useradd --create-home --uid 10001 orgweave
USER 10001

CMD ["sh", "-c", "python -m $WORKER_MODULE"]
