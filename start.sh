#!/bin/bash
set -e

# Wait for services using Python script (more reliable)
echo "Waiting for services to be ready..."
python3 wait_for_services.py qdrant 6333 mongodb 27017

if [ $? -ne 0 ]; then
    echo "Failed to wait for services. Exiting."
    exit 1
fi

echo "All services are ready. Starting backend..."

# Enable hot-reload in development by setting UVICORN_RELOAD=true.
# Requires the source bind mount (.:/app) so edits are visible inside the container.
RELOAD_FLAG=""
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
    echo "Hot-reload enabled (UVICORN_RELOAD=true)."
    RELOAD_FLAG="--reload"
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000 ${RELOAD_FLAG}
