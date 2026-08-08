# Multi-stage build for production
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY control-panel/backend/requirements.txt /app/backend/requirements.txt
COPY agent/requirements.txt /app/agent/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt && \
    pip install --no-cache-dir -r /app/agent/requirements.txt

# Production stage
FROM python:3.12-slim as production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY control-panel/backend /app/control-panel/backend
COPY control-panel/frontend /app/control-panel/frontend
COPY agent /app/agent
COPY scripts /app/scripts

# Create non-root user
RUN useradd -m -u 1000 substrate && \
    chown -R substrate:substrate /app

USER substrate

# Expose ports
EXPOSE 8080 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command
CMD ["python", "-m", "uvicorn", "control-panel.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
