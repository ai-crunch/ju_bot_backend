from models.user import User, UserDB


class TestUserModel:
    def test_create_user(self, user_db: UserDB):
        user = User(
            username="newuser",
            email="new@ju.edu.jo",
            hashed_password=User.hash_password("pass123"),
        )
        user_id = user_db.create_user(user)
        assert user_id is not None
        fetched = user_db.get_user_by_id(user_id)
        assert fetched["username"] == "newuser"

    def test_duplicate_username_raises(self, user_db: UserDB, sample_user: dict):
        user = User(
            username=sample_user["username"],
            email="other@ju.edu.jo",
            hashed_password="hash",
        )
        import pymongo.errors
        with pytest.raises(pymongo.errors.DuplicateKeyError):
            user_db.create_user(user)

    def test_get_user_by_id(self, user_db: UserDB, sample_user: dict):
        fetched = user_db.get_user_by_id(sample_user["user_id"])
        assert fetched is not None
        assert fetched["email"] == "test@ju.edu.jo"

    def test_get_user_by_username(self, user_db: UserDB, sample_user: dict):
        fetched = user_db.get_user_by_username(sample_user["username"])
        assert fetched is not None
        assert fetched["user_id"] == sample_user["user_id"]

    def test_get_user_by_email(self, user_db: UserDB, sample_user: dict):
        fetched = user_db.get_user_by_email(sample_user["email"])
        assert fetched is not None
        assert fetched["username"] == "testuser"

    def test_get_all_users(self, user_db: UserDB, sample_user: dict):
        users = user_db.get_all_users()
        assert len(users) >= 1
        assert any(u["user_id"] == sample_user["user_id"] for u in users)

    def test_update_user(self, user_db: UserDB, sample_user: dict):
        result = user_db.update_user(sample_user["user_id"], username="updated_user")
        assert result is True
        fetched = user_db.get_user_by_id(sample_user["user_id"])
        assert fetched["username"] == "updated_user"

    def test_update_user_duplicate_email(self, user_db: UserDB):
        u1 = User(username="u1", email="a@ju.edu.jo", hashed_password="h1")
        user_db.create_user(u1)
        u2 = User(username="u2", email="b@ju.edu.jo", hashed_password="h2")
        user_db.create_user(u2)

        u1_data = user_db.get_user_by_username("u1")
        result = user_db.update_user(u2.user_id, email=u1_data["email"])
        assert result is False

    def test_change_password(self, user_db: UserDB, sample_user: dict):
        new_hash = User.hash_password("NewPass456!")
        result = user_db.change_password(sample_user["user_id"], new_hash)
        assert result is True
        fetched = user_db.get_user_by_id(sample_user["user_id"])
        assert User.verify_password("NewPass456!", fetched["hashed_password"])


class TestUserAPIKey:
    def test_ensure_api_key_generates(self, user_db: UserDB, sample_user: dict):
        key = user_db.ensure_api_key(sample_user["user_id"])
        assert key is not None
        assert len(key) > 10

    def test_get_user_by_api_key(self, user_db: UserDB, sample_user: dict):
        key = user_db.ensure_api_key(sample_user["user_id"])
        fetched = user_db.get_user_by_api_key(key)
        assert fetched is not None
        assert fetched["user_id"] == sample_user["user_id"]

    def test_invalid_api_key(self, user_db: UserDB):
        fetched = user_db.get_user_by_api_key("nonexistent-key")
        assert fetched is None


class TestUserRoles:
    def test_default_role_is_user(self, user_db: UserDB, sample_user: dict):
        assert sample_user["role"] == "user"
        assert sample_user["is_admin"] is False

    def test_set_user_role_to_admin(self, user_db: UserDB, sample_user: dict):
        user_db.set_user_role(sample_user["user_id"], "admin")
        fetched = user_db.get_user_by_id(sample_user["user_id"])
        assert fetched["role"] == "admin"
        assert fetched["is_admin"] is True

    def test_set_user_role_with_department(self, user_db: UserDB, sample_user: dict):
        user_db.set_user_role(
            sample_user["user_id"],
            "department_editor",
            department_id="dept_1",
            department_name="Computer Science",
        )
        fetched = user_db.get_user_by_id(sample_user["user_id"])
        assert fetched["role"] == "department_editor"
        assert fetched["department_id"] == "dept_1"
        assert fetched["department_name"] == "Computer Science"


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = User.hash_password("MyPassword123!")
        assert User.verify_password("MyPassword123!", hashed)
        assert not User.verify_password("WrongPassword", hashed)

    def test_hash_is_different_each_time(self):
        h1 = User.hash_password("same_password")
        h2 = User.hash_password("same_password")
        assert h1 != h2


import pytest
