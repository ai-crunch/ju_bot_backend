# JU Bot Backend

AI-powered assistant backend for the University of Jordan.

## Setup

1.  **Environment Variables**: Create a `.env` file in the root directory based on `.env.example`.
2.  **Virtual Environment**: 
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Seed Admin User**:
    To create the initial admin user, run the following script:
    ```bash
    python seed_admin.py
    ```
    By default, it creates an admin with:
    - **Username**: `admin`
    - **Password**: `admin`
    
    You can customize these by setting environment variables `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`.

## Running the Application

```bash
python main.py
```
