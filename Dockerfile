# syntax=docker/dockerfile:1.7
FROM python:3.11-slim as build 

# Set working directory
WORKDIR /app

# Install system dependencies.
# Cache mounts keep apt's package lists/archives across builds for fast rebuilds.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies.
# pip cache mount avoids re-downloading wheels when requirements are unchanged.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Copy wait script
COPY wait_for_services.py wait_for_services.py

# Create necessary directories
RUN mkdir -p data logs ocr_results

# Expose port
EXPOSE 8000

# Health check (stdlib urllib only — no dependency on `requests` being importable)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/').status==200 else 1)" || exit 1

# Copy start script
COPY start.sh /start.sh

# Normalize line endings (strip Windows CRLF -> LF) so the scripts run under
# Linux even when authored/checked out on Windows, then make them executable.
RUN sed -i 's/\r$//' /start.sh /app/seed.sh /app/wait_for_services.py \
    && chmod +x /start.sh /app/seed.sh

# Run the application
CMD ["/start.sh"]
