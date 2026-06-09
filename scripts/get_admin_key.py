from models.database import MongoDB

db = MongoDB.get_db()
users = db["users"]

admin = users.find_one({"is_admin": True}, {"_id": 0, "username": 1, "api_key": 1})
if admin:
    print(f"Admin user: {admin['username']}")
    print(f"API key: {admin['api_key']}")
else:
    print("No admin user found")
