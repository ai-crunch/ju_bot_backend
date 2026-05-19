import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Add the current directory to sys.path to import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.user import User, UserDB
from models.database import MongoDB
from datetime import datetime


def seed_admin(username="admin", email="admin@ju.edu.jo", password="admin"):
    """
    Seeds an admin user into the MongoDB database if it doesn't already exist.
    """
    try:
        user_db = UserDB()

        # Check if admin already exists by username
        existing_user = user_db.get_user_by_username(username)
        if existing_user:
            print(f"⚠️ User '{username}' already exists. Skipping seeding.")
            return

        # Hash the password
        hashed_password = User.hash_password(password)

        # Create admin user object
        admin_user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            role="admin",
            is_admin=True,
            created_at=datetime.utcnow(),
        )

        # Insert into DB
        user_id = user_db.create_user(admin_user)
        print(f"✅ Admin user '{username}' created successfully with ID: {user_id}")

    except Exception as e:
        print(f"❌ Error seeding admin user: {e}")


if __name__ == "__main__":
    # You can change these default values if needed
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@ju.edu.jo")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

    print("🚀 Seeding admin user...")
    seed_admin(ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD)
