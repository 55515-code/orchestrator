FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG SUBSTRATE_UID=1000
ARG SUBSTRATE_GID=1000
ARG UV_VERSION=0.12.5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN addgroup --gid "${SUBSTRATE_GID}" substrate && \
    adduser --uid "${SUBSTRATE_UID}" --gid "${SUBSTRATE_GID}" \
      --disabled-password --gecos "" --home /home/substrate substrate && \
    mkdir -p /app/state /app/memory /app/artifacts /app/.research && \
    chown -R substrate:substrate /app /home/substrate

USER substrate

EXPOSE 8080

CMD ["sh", "-c", "uv run python scripts/substrate_cli.py serve --host 0.0.0.0 --port ${PORT:-8080}"]
