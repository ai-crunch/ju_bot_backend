import mongomock
import pytest
from models.user import UserDB


@pytest.fixture(autouse=True)
def mock_mongodb(monkeypatch):
    client = mongomock.MongoClient()
    db = client["ju_bot_test"]
    monkeypatch.setattr("models.database.MongoDB.get_db", lambda: db)
    yield db
    client.drop_database("ju_bot_test")


@pytest.fixture
def user_db(mock_mongodb):
    return UserDB()


@pytest.fixture
def sample_user(user_db):
    from models.user import User
    user = User(
        username="testuser",
        email="test@ju.edu.jo",
        hashed_password=User.hash_password("TestPass123!"),
        role="user",
    )
    user_db.create_user(user)
    return user_db.get_user_by_id(user.user_id)
