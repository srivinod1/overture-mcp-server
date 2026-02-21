FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for DuckDB spatial extension
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files needed for pip install (hatchling needs README + src/)
COPY pyproject.toml README.md ./
COPY src/ src/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Default environment: SSE transport, port 8000
ENV TRANSPORT=sse
ENV PORT=8000
EXPOSE 8000

# Health check (generous start-period for DuckDB S3 cold start)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start server
CMD ["python", "-m", "overture_mcp.server"]
