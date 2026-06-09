from models.user import UserDB

user_db = UserDB()
user = user_db.get_user_by_api_key("fb245599-8644-433b-b984-6278123bcf7f")
if user:
    import json
    try:
        json.dumps(user)
        print("User dict is JSON serializable")
    except Exception as e:
        print(f"User dict is NOT JSON serializable: {e}")
    for k, v in user.items():
        print(f"{k}: type={type(v).__name__}")
else:
    print("User not found")
