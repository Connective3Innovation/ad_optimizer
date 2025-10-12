# Multi-stage build for smaller runtime image
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# System deps (add tesseract for optional OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Streamlit binds to $PORT (Cloud Run) or 8080
CMD ["bash","-lc","exec streamlit run src/app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true"]

