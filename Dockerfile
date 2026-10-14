# thai-writing-quality MCP server — Streamable HTTP, authenticated, loopback-default
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY skills ./skills
RUN pip install --no-cache-dir .

# Non-root user
RUN useradd --create-home --shell /usr/sbin/nologin mcp && chown -R mcp:mcp /app
USER mcp

ENV TWQ_HTTP_HOST=0.0.0.0 \
    TWQ_HTTP_PORT=8000
# TWQ_HTTP_API_KEY MUST be provided at runtime (secret manager); without it
# the app refuses every request (fail closed).

EXPOSE 8000
# Liveness probe against the real server (unauthenticated GET /healthz),
# not just an environment-variable check.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 --start-period=5s \
  CMD python -c "import urllib.request; \
r = urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2); \
assert r.status == 200, r.status" || exit 1

CMD ["thai-writing-http"]
