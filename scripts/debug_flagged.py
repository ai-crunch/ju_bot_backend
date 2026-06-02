from models.database import MongoDB
from datetime import datetime
from bson import ObjectId

db = MongoDB.get_db()
msgs = db["messages"]
chats = db["chats"]

pipeline = [
    {"$match": {"role": "assistant", "dislikes_count": {"$gte": 1}}},
    {"$sort": {"dislikes_count": -1, "timestamp": -1}},
    {"$limit": 50},
    {"$project": {
        "_id": 0,
        "message_id": 1,
        "chat_id": 1,
        "content": 1,
        "timestamp": 1,
        "likes_count": {"$ifNull": ["$likes_count", 0]},
        "dislikes_count": {"$ifNull": ["$dislikes_count", 0]},
        "feedback": {"$ifNull": ["$feedback", 0]},
        "sources": 1,
    }},
]

raw_flagged = list(msgs.aggregate(pipeline))
print(f"raw_flagged count: {len(raw_flagged)}")

for i, f in enumerate(raw_flagged):
    print(f"Item {i}:")
    for k, v in f.items():
        print(f"  {k}: type={type(v).__name__} value={v}")
    print()

chat_ids = [f["chat_id"] for f in raw_flagged]
chat_titles = {
    str(c["chat_id"]): c.get("title", "Untitled")
    for c in chats.find({"chat_id": {"$in": chat_ids}}, {"_id": 0, "chat_id": 1, "title": 1})
}

flagged = []
for f in raw_flagged:
    ts = f.get("timestamp")
    flagged.append({
        "message_id": str(f["message_id"]),
        "chat_id": str(f["chat_id"]),
        "content": str(f.get("content", "")),
        "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        "likes_count": int(f.get("likes_count", 0)),
        "dislikes_count": int(f.get("dislikes_count", 0)),
        "feedback": int(f.get("feedback", 0)),
        "sources": [],
        "chat_title": chat_titles.get(str(f["chat_id"]), "Untitled"),
    })

print("Final flagged structure:")
for item in flagged:
    print(item)
