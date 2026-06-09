from models.database import MongoDB

db = MongoDB.get_db()
msgs = db["messages"]

# Check if any assistant messages have cached_from_message_id
with_field = list(msgs.find({"cached_from_message_id": {"$exists": True}}, {"_id": 0, "message_id": 1, "cached_from_message_id": 1, "content": 1}).limit(10))
print(f"Messages with cached_from_message_id field: {len(with_field)}")
for doc in with_field:
    print(doc)

# Check distinct values
print("\nDistinct cached_from_message_id values:")
print(msgs.distinct("cached_from_message_id", {"cached_from_message_id": {"$ne": None}}))
