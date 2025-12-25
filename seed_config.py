import sys
import os
from pymongo import MongoClient
import dotenv

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

dotenv.load_dotenv()


def seed_system_config():
    """
    Seeds the initial system configuration into MongoDB.
    """
    mongo_host = os.getenv("MONGO_HOST", "localhost")
    mongo_port = int(os.getenv("MONGO_PORT", 27077))
    mongo_user = os.getenv("MONGO_ROOT_USERNAME", "admin")
    mongo_pass = os.getenv("MONGO_ROOT_PASSWORD", "password")
    mongo_db_name = os.getenv("MONGO_DATABASE", "ju_bot_feedback")

    connection_string = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/{mongo_db_name}?authSource=admin"

    try:
        client = MongoClient(connection_string)
        db = client[mongo_db_name]
        collection = db["system_config"]

        # Current default values from config.py
        initial_config = {
            "config_id": "main_config",
            "embedding": {
                "provider": "huggingface",
                "model_name": "intfloat/multilingual-e5-small",
            },
            "retrieval": {
                "chunk_size": 300,
                "chunk_overlap": 50,
                "retrieved_chunks": 5,
                "chunk_threshold": 300,
            },
            "llm": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.0,
                "api_key": os.getenv("OPENAI_API_KEY"),
            },
            "vector_db": {
                "host": os.getenv("QDRANT_HOST", "localhost"),
                "port": int(os.getenv("QDRANT_PORT", 6333)),
                "collection_name": "ju_bot_vdb_with_ocr_test_generator",
            },
            "system_flags": {
                "maintenance_mode": False,
                "debug": False,
                "enable_ocr": True,
                "enable_reasoning": False,
            },
        }

        # Check if config already exists
        if collection.find_one({"config_id": "main_config"}):
            print("⚠️ System configuration already exists. Updating defaults...")
            collection.update_one(
                {"config_id": "main_config"}, {"$set": initial_config}
            )
            print("✅ System configuration updated successfully.")
            return

        collection.insert_one(initial_config)
        print("✅ System configuration seeded successfully.")

    except Exception as e:
        print(f"❌ Error seeding system configuration: {e}")


if __name__ == "__main__":
    print("🚀 Seeding system configuration...")
    seed_system_config()
