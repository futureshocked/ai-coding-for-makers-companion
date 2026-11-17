FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

FROM base AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev gcc \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM base AS runtime
COPY --from=build /install /usr/local
COPY . /app

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    FLASK_APP=wsgi.py \
    PYTHONPATH=/app

RUN useradd --system --uid 1000 --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/app/static/uploads/resources \
 && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
