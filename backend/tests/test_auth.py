"""Tests for the lightweight auth service and routes."""
import pytest

from app.models import User
from app.services.auth import (
    create_token,
    hash_password,
    user_can_access_session,
    verify_password,
    verify_token,
)


class TestPasswordHashing:
    def test_roundtrip(self):
        stored = hash_password("secret123")
        assert verify_password("secret123", stored)
        assert not verify_password("wrong", stored)

    def test_malformed_stored_hash_rejected(self):
        assert not verify_password("secret123", "not-a-hash")

    def test_unique_salts(self):
        assert hash_password("same") != hash_password("same")


class TestTokens:
    def _user(self, **kw):
        u = User()
        u.id = kw.get("id", 7)
        u.username = kw.get("username", "s1")
        u.role = kw.get("role", "student")
        return u

    def test_roundtrip(self):
        token = create_token(self._user())
        payload = verify_token(token)
        assert payload and payload["sub"] == 7 and payload["role"] == "student"

    def test_tampered_signature_rejected(self):
        token = create_token(self._user())
        body, sig = token.split(".")
        assert verify_token(f"{body}.{sig[:-2]}xx") is None

    def test_garbage_rejected(self):
        assert verify_token("not-a-token") is None
        assert verify_token("") is None


class TestAccessRule:
    def _user(self, uid=1, role="student"):
        u = User()
        u.id, u.role = uid, role
        return u

    def test_owner_and_shared(self):
        from app.models import Session as SessionModel

        user = self._user(uid=1)
        mine = SessionModel(id="a", user_id=1)
        shared = SessionModel(id="b", user_id=None)
        theirs = SessionModel(id="c", user_id=2)
        assert user_can_access_session(user, mine)
        assert user_can_access_session(user, shared)
        assert not user_can_access_session(user, theirs)

    def test_admin_sees_everything(self):
        from app.models import Session as SessionModel

        admin = self._user(uid=9, role="admin")
        assert user_can_access_session(admin, SessionModel(id="c", user_id=2))


class TestAuthEndpoints:
    def test_login_me_flow(self, client, db_session):
        db_session.add(User(username="stu1", password_hash=hash_password("pass123"), role="student"))
        db_session.commit()

        bad = client.post("/api/v1/auth/login", json={"username": "stu1", "password": "nope"})
        assert bad.status_code == 401

        ok = client.post("/api/v1/auth/login", json={"username": "stu1", "password": "pass123"})
        assert ok.status_code == 200
        token = ok.json()["token"]
        assert ok.json()["user"]["username"] == "stu1"

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["role"] == "student"

    def test_user_management_requires_admin(self, client, db_session):
        db_session.add(User(username="stu2", password_hash=hash_password("pass123"), role="student"))
        db_session.add(User(username="boss", password_hash=hash_password("boss123"), role="admin"))
        db_session.commit()

        stu_token = client.post(
            "/api/v1/auth/login", json={"username": "stu2", "password": "pass123"}
        ).json()["token"]
        denied = client.post(
            "/api/v1/auth/users",
            json={"username": "x1", "password": "pass123"},
            headers={"Authorization": f"Bearer {stu_token}"},
        )
        assert denied.status_code == 403

        admin_token = client.post(
            "/api/v1/auth/login", json={"username": "boss", "password": "boss123"}
        ).json()["token"]
        created = client.post(
            "/api/v1/auth/users",
            json={"username": "x1", "password": "pass123"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert created.status_code == 201
        dupe = client.post(
            "/api/v1/auth/users",
            json={"username": "x1", "password": "pass123"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dupe.status_code == 409
