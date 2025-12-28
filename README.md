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
3. **Docker Services**:
    ```
    cd docker
    docker compose --env-file ../.env up -d
    ```

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
