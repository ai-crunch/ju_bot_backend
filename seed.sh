#!/bin/bash
# One-shot, idempotent bootstrap for the JU Bot stack.
#
# Order matters:
#   1. seed_admin.py    -> creates the admin user (skips if it already exists)
#   2. seed_config.py   -> writes the SystemConfig document (config.py reads this)
#   3. generator.py     -> populates the Qdrant vector DB (only when empty)
#
# Safe to re-run: admin/config seeding is skip-or-update, and the generator is
# guarded so the expensive embedding pass is skipped once the collection is filled.
set -e

echo "[seed] Waiting for MongoDB and Qdrant..."
python3 wait_for_services.py "${QDRANT_HOST:-qdrant}" "${QDRANT_PORT:-6333}" "${MONGO_HOST:-mongodb}" "${MONGO_PORT:-27017}"

echo "[seed] Seeding admin user..."
python3 seed_admin.py

echo "[seed] Seeding system configuration..."
python3 seed_config.py

echo "[seed] Checking whether the vector DB needs indexing..."
NEEDS_INDEX=$(python3 - <<'PY'
import os
from qdrant_client import QdrantClient

host = os.getenv("QDRANT_HOST", "qdrant")
port = int(os.getenv("QDRANT_PORT", "6333"))
collection = os.getenv("QDRANT_COLLECTION_NAME", "ju_bot_vdb")

try:
    client = QdrantClient(host=host, port=port)
    count = client.count(collection).count if client.collection_exists(collection) else 0
except Exception:
    # If the collection is missing or unreachable, treat it as needing indexing.
    count = 0

print("yes" if count == 0 else "no")
PY
)

if [ "${NEEDS_INDEX}" = "yes" ]; then
    echo "[seed] Vector DB is empty -> running generator (this can take several minutes)..."
    python3 generator.py
else
    echo "[seed] Vector DB already populated -> skipping generator."
fi

echo "[seed] Bootstrap complete."
