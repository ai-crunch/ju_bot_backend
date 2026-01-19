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
exec uvicorn main:app --host 0.0.0.0 --port 8000
