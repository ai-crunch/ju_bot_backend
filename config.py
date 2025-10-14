import dotenv
import os

dotenv.load_dotenv()

DATA_DIR_PATH = os.path.join("data")

QDRANT = {
    "host": os.getenv("QDRANT_HOST", "localhost"),
    "port": int(os.getenv("QDRANT_PORT", 6333)),
    "collection_name": "ju_bot_vdb",
}

EMBEDDER = {
    "model_name": "intfloat/multilingual-e5-small",
}

OPENAI = {
    "model": "gpt-4o-mini",
    "api_key": os.getenv("OPENAI_API_KEY"),
}

MONGODB = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", 27017)),
    "username": os.getenv("MONGO_ROOT_USERNAME", "admin"),
    "password": os.getenv("MONGO_ROOT_PASSWORD", "password"),
    "database": os.getenv("MONGO_DATABASE", "ju_bot_feedback"),
    "collection": "feedback_data",
}
