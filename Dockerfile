FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    NEOGEN_DATA_DIR=/var/lib/neogen \
    GENESIS_WORKSPACE_DIR=/var/lib/neogen/workspace

RUN groupadd --system neogen && useradd --system --gid neogen --home /app neogen

WORKDIR /app
COPY pyproject.toml README.md ./
COPY genesis ./genesis
COPY web ./web
RUN python -m pip install --no-cache-dir .

RUN mkdir -p /var/lib/neogen/workspace && chown -R neogen:neogen /var/lib/neogen /app
USER neogen

EXPOSE 8080
VOLUME ["/var/lib/neogen"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health',timeout=4); assert r.status == 200; json.load(r)"

CMD ["python", "-m", "genesis.production"]
