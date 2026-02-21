# Deployment Guide

This guide covers deploying the Overture Maps MCP Server to Railway.

---

## Prerequisites

- [Railway account](https://railway.app/) (Hobby plan: $5/month)
- [Railway CLI](https://docs.railway.app/develop/cli) installed
- GitHub repository connected to Railway

---

## Environment Variables

Set these in the Railway dashboard under your service's Variables tab:

| Variable | Required | Value | Notes |
|----------|----------|-------|-------|
| `OVERTURE_API_KEY` | Yes | Your chosen API key | Shared with MCP clients |
| `TOOL_MODE` | No | `direct` | `direct` (default) or `progressive` |
| `OVERTURE_DATA_VERSION` | No | `2026-01-21.0` | Override to use different Overture release |
| `MAX_CONCURRENT_QUERIES` | No | `3` | DuckDB query concurrency limit |
| `MAX_RADIUS_M` | No | `50000` | Safety cap on radius queries |
| `PORT` | No | `8000` | Railway sets this automatically |

**No AWS credentials needed** — Overture's S3 bucket is publicly accessible.

---

## Deployment Steps

### 1. Connect Repository

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project
railway link
```

### 2. Configure Railway

The `railway.toml` in the repo root configures the deployment:

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "python -m overture_mcp.server"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### 3. Deploy

```bash
# Deploy from current branch
railway up

# Or push to GitHub — Railway auto-deploys from connected repo
git push origin main
```

### 4. Set Environment Variables

```bash
railway variables set OVERTURE_API_KEY=your-secret-key-here
```

### 5. Verify

```bash
# Get your deployment URL
railway status

# Test health endpoint
curl https://your-app.up.railway.app/health

# Expected response:
# {"status": "healthy", "data_version": "2026-01-21.0", "uptime_seconds": 42}
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for DuckDB spatial
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY src/ src/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start server
CMD ["python", "-m", "overture_mcp.server"]
```

**Note**: The `start-period=60s` is generous because the first DuckDB query (during health check) needs to establish S3 connections and read Parquet metadata.

---

## Resource Requirements

### Minimum (Railway Hobby)
- **RAM**: 512 MB (DuckDB uses memory for query processing)
- **CPU**: 1 vCPU
- **Disk**: Minimal (no persistent storage — all data from S3)

### Recommended
- **RAM**: 1 GB (allows 3 concurrent queries without memory pressure)
- **CPU**: 1 vCPU (queries are I/O-bound on S3, not CPU-bound)

### Cost Estimate
- Railway Hobby plan: $5/month base
- Usage-based: ~$2-5/month depending on query volume
- S3 reads: ~$0 (Overture is public, egress from us-west-2 is minimal)
- **Total: ~$7-10/month**

---

## Monitoring

### Health Endpoint
`GET /health` returns:
```json
{
  "status": "healthy",
  "data_version": "2026-01-21.0",
  "uptime_seconds": 3600
}
```

### Logs
Railway captures stdout/stderr automatically. The server logs:
- Startup (extensions loaded, S3 connectivity confirmed)
- Each tool call (tool name, query params, latency)
- Errors (S3 timeouts, query failures)

View logs:
```bash
railway logs
```

---

## Updating Overture Data Version

When a new Overture release drops (quarterly):

1. Update the `OVERTURE_DATA_VERSION` environment variable:
   ```bash
   railway variables set OVERTURE_DATA_VERSION=2026-04-21.0
   ```
2. Restart the service:
   ```bash
   railway service restart
   ```
3. Verify with health check.

No code changes needed. No data migration. The server reads the version from the environment variable and constructs S3 paths accordingly.

---

## Connecting Clients

### Claude Desktop
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "overture-maps": {
      "url": "https://your-app.up.railway.app/sse",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

### Claude Code
Add to MCP settings:
```json
{
  "mcpServers": {
    "overture-maps": {
      "url": "https://your-app.up.railway.app/sse",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

### Any MCP Client
The server exposes SSE transport at `/sse`. Connect with any MCP-compatible client using:
- **URL**: `https://your-app.up.railway.app/sse`
- **Header**: `X-API-Key: your-api-key`

---

## Troubleshooting

### Server won't start
- Check `railway logs` for Python import errors
- Verify Dockerfile builds locally: `docker build -t overture-mcp .`

### Queries timeout (30s)
- S3 cold starts can be slow. First query after deploy may take 10-15s.
- If persistent, reduce `MAX_CONCURRENT_QUERIES` to `1` to lower memory pressure.
- Check if the radius is too large (>10km on buildings theme is expensive).

### Out of memory
- Reduce `MAX_CONCURRENT_QUERIES` to `2` or `1`
- Upgrade Railway plan for more RAM
- Large building queries (>5km radius) consume significant memory

### Health check fails
- The `/health` endpoint runs a trivial DuckDB query against S3
- On cold start, this can take up to 60s (hence the generous `start-period`)
- If it keeps failing, check S3 connectivity (Overture bucket availability)

### Authentication errors
- Verify `OVERTURE_API_KEY` is set in Railway variables
- Verify client sends `X-API-Key` header with matching value
- Check for trailing whitespace in the API key
