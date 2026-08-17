# ---- builder: resolves/installs dependencies into a venv -------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps ./apps
COPY config ./config
COPY manage.py ./
RUN uv sync --frozen --no-dev

# ---- runtime: just the venv + source, no uv/compiler/lockfile --------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.production

RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# WORKDIR above created /app as root before the COPY ran; --chown on COPY
# only sets ownership on what it copies IN, not on that pre-existing
# directory entry itself, so /app stays root-owned unless fixed explicitly.
# Left alone, gunicorn (running as `app`, HOME=/app) can't write its own
# control-server file directly into its home directory. (Same bug hit and
# fixed the same way in the inventra-django port.)
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown app:app /app \
    && mkdir -p /app/staticfiles && chown app:app /app/staticfiles

USER app

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
