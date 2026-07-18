# --- builder stage: install deps into a venv ---
FROM python:3.12-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY services/auth-service/requirements.txt ./requirements.txt
# requirements.txt's `-e ../../libs/shared_auth` resolves relative to this
# stage's WORKDIR (/build), i.e. up to /, so shared_auth must land at
# /libs/shared_auth, not /build/libs/shared_auth - matching the real repo's
# services/<name>/../../libs/shared_auth layout one level "shallower" than
# WORKDIR here.
COPY libs/shared_auth /libs/shared_auth

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- runtime stage: slim image, no compilers ---
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv
# `pip install -e` doesn't copy shared_auth into site-packages - it only
# adds a path reference to wherever it was installed from. That source
# directory has to exist here too, at the same absolute path, or every
# `import shared_auth` fails at runtime even though the image built fine.
COPY --from=builder /libs/shared_auth /libs/shared_auth
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1

WORKDIR /app
COPY services/auth-service/app ./app
COPY services/auth-service/alembic ./alembic
COPY services/auth-service/alembic.ini .

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
