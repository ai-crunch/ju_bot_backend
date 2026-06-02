# JU Bot Backend

AI-powered assistant backend for the University of Jordan.

## Setup

1.  **Environment Variables**: Create a `.env` file in the root directory based on `.env.example`.
2.  **Virtual Environment**: 
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt
    ```
3. **Docker Services** (compose lives at the repo root):
    ```
    cd ..
    docker compose --env-file ju_bot_backend/.env up -d
    ```
    > The `seed` service runs steps 4–6 below automatically and idempotently
    > (admin user → system config → vector DB) once MongoDB/Qdrant are healthy.
    > Steps 4–6 are only needed for local (non-Docker) runs.

4.  **Seed Admin User**:
    To create the initial admin user, run the following script:
    ```bash
    python seed_admin.py
    ```
    By default, it creates an admin with:
    - **Username**: `admin`
    - **Password**: `admin`
    
    You can customize these by setting environment variables `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`.

5. **Seed Configuration:
    ```
    python3 seed_config.py
    ```

6. **Populate the VDB**:
    ```
    python3 generator.py
    ```

## Running the Application

```bash
python main.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Docker Build Optimization & Dev Hot-Reload

The Dockerfiles use BuildKit cache mounts (pip, apt, npm) so that repeat builds reuse
downloaded packages instead of re-fetching them. To benefit from these:

1. **Enable BuildKit** (default on Docker 23+; set explicitly otherwise) and optionally Bake:
   ```bash
   export DOCKER_BUILDKIT=1
   export COMPOSE_BAKE=true   # parallel multi-service builds
   ```
   These are also documented in `.env.example`.

2. **Build** (the compose files live at the repo root; run from there):
   ```bash
   cd ..
   docker compose --env-file ju_bot_backend/.env build
   ```
   The first build populates the caches; a second build with unchanged
   `requirements.txt` / `package-lock.json` is near-instant (cache hits).

3. **Dev hot-reload**: the `backend` service bind-mounts the source
   (`./ju_bot_backend:/app`). Set `UVICORN_RELOAD=true` to run `uvicorn --reload`,
   so code edits take effect without rebuilding the image:
   ```bash
   UVICORN_RELOAD=true docker compose --env-file ju_bot_backend/.env up
   ```
