# Multi-stage Dockerfile for Worker API
# Build context: project root (.)

# Stage 1: Builder
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements
COPY qwertyworkforever.top/requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set PATH to use virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 appuser

# Create working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser qwertyworkforever.top/api /app/api
COPY --chown=appuser:appuser shared/api/common /app/api/common
COPY --chown=appuser:appuser shared/database /app/database

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8003

# Run application
CMD ["sh", "-c", "uvicorn api.worker.main:app --host 0.0.0.0 --port 8003 --workers ${UVICORN_WORKERS:-2} --timeout-keep-alive 5 --log-level info"]
