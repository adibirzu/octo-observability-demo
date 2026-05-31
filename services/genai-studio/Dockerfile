# OCTO Drone Shop — AI Studio (GenAI multi-agent) service
# Build x86_64 on the control-plane VM (Apple Silicon dev box must not QEMU-build).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: matplotlib needs no extra libs on slim for Agg; keep image lean.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install \
        "fastapi==0.136.3" "uvicorn[standard]==0.48.0" "httpx==0.28.1" \
        "pydantic>=2.9,<3.0" "python-multipart==0.0.29" \
        "langchain>=0.3.0" "langchain-core>=0.3.0" "langgraph>=0.2.0" \
        "langchain-oci>=0.2.6,<0.3.0" \
        "oci>=2.120.0" "oracledb>=2.0.0" \
        "pandas>=2.2.0" "matplotlib>=3.9.0" \
        "opentelemetry-api>=1.27.0" "opentelemetry-sdk>=1.27.0" \
        "opentelemetry-exporter-otlp-proto-http>=1.27.0" \
        "opentelemetry-instrumentation-fastapi>=0.48b0" \
        "opentelemetry-instrumentation-httpx>=0.48b0" \
        "langfuse>=4.0.1"

COPY app ./app

USER appuser
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
