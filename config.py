import dotenv
import os

dotenv.load_dotenv()

DATA_DIR_PATH = os.path.join("data")

QDRANT = {
    "host": "localhost",
    "port": 6333,
    "collection_name": "ju_bot_vdb",
}

EMBEDDER = {
    "model_name": "intfloat/multilingual-e5-small",
}

OPENAI = {
    "model": "gpt-4o-mini",
    "api_key": os.getenv("OPENAI_API_KEY"),
}
