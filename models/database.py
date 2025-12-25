from pymongo import MongoClient
from typing import Optional


class MongoDB:
    """Base class for MongoDB connection"""

    _instance: Optional[MongoClient] = None

    @classmethod
    def get_client(cls) -> MongoClient:
        if cls._instance is None:
            import config

            mongo_config = config.MONGODB
            try:
                # Try configured credentials first
                auth_connection = f"mongodb://{mongo_config['username']}:{mongo_config['password']}@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
                cls._instance = MongoClient(auth_connection)
                cls._instance.admin.command("ping")
            except Exception:
                try:
                    # Fallback to no authentication
                    simple_connection = (
                        f"mongodb://{mongo_config['host']}:{mongo_config['port']}"
                    )
                    cls._instance = MongoClient(simple_connection)
                    cls._instance.admin.command("ping")
                except Exception as e:
                    print(f"❌ Failed to connect to MongoDB: {e}")
                    raise e
        return cls._instance

    @classmethod
    def get_db(cls):
        import config

        client = cls.get_client()
        return client[config.MONGODB["database"]]
