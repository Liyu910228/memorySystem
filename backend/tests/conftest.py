import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = ""
os.environ["MEMORY_EXPORT_DIR"] = "D:/liyucode/memorySystem/backend/test-data/memories"

from app.main import app
from app.shared.database import Base, get_db
from app.shared.models import Role, User
from app.shared.security import hash_password


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestingSessionLocal() as db:
        db.add_all(
            [
                User(username="admin", display_name="Admin", password_hash=hash_password("admin123"), role=Role.admin.value),
                User(username="ldap:alice001", ldap_id="alice001", display_name="Alice", password_hash=None, role=Role.employee.value),
                User(username="ldap:bob001", ldap_id="bob001", display_name="Bob", password_hash=None, role=Role.employee.value),
            ]
        )
        db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def token(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
