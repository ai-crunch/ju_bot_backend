from models.database import MongoDB
from bson import ObjectId

db = MongoDB.get_db()
msgs = db["messages"]

# Get a sample assistant message with dislikes
sample = msgs.find_one({"role": "assistant", "dislikes_count": {"$gt": 0}})
if sample:
    print("Sources field:")
    print(sample.get("sources"))
    if sample.get("sources"):
        print("First source type:", type(sample["sources"][0]))
        print("First source keys:", sample["sources"][0].keys() if hasattr(sample["sources"][0], "keys") else "N/A")
else:
    print("No sample found")
