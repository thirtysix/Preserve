# Preserve API gateway image.
FROM python:3.12-slim

WORKDIR /app

# Install only what the API needs (no spaCy/llama-cpp).
COPY setup.py README.md ./
COPY preserve ./preserve
RUN pip install --no-cache-dir -e ".[api,redis]"

# Pre-warm the names-dataset / wordfreq caches so the first request isn't slow.
RUN python -c "from preserve import Scrubber, PreserveConfig, SensitivityLevel; \
    Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE)).scrub('warm up Jane Doe')"

ENV PRESERVE_API_HOST=0.0.0.0 \
    PRESERVE_API_PORT=8800

EXPOSE 8800

# Healthcheck hits the liveness endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8800/health').status==200 else 1)"

CMD ["uvicorn", "preserve.api.app:app", "--host", "0.0.0.0", "--port", "8800"]
