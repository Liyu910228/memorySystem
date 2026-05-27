from datetime import datetime, timedelta, timezone

from jose import jwt

from app.main import app
from app.shared.database import get_db
from app.shared.models import Memory, MemoryLayer, MemoryStatus, User
from tests.conftest import token


def external_token(ldap_id: str, audience_field: str = "aud") -> str:
    payload = {audience_field: ldap_id} if audience_field else {"sub": ldap_id}
    return jwt.encode(payload, "external-secret", algorithm="HS256")


def open_test_db_session():
    override = app.dependency_overrides[get_db]
    generator = override()
    return generator, next(generator)


def test_dialogue_memory_public_read_returns_markdown_by_ldap_id(client):
    alice = client.post(
        "/api/dialogue-memories",
        json={"ldapId": "alice001", "question": "remember: I prefer concise Chinese answers."},
    )
    assert alice.status_code == 200
    assert alice.json()["saved"] >= 1

    bob = client.get("/api/dialogue-memories/bob001")
    alice_memories = client.get("/api/dialogue-memories/alice001")
    assert bob.status_code == 200
    assert bob.json()["ldapId"] == "bob001"
    assert "暂无可用记忆" in bob.json()["content"]
    assert alice_memories.status_code == 200
    assert alice_memories.json()["ldapId"] == "alice001"
    assert "# alice001 的个人记忆汇总" in alice_memories.json()["content"]
    assert "concise Chinese answers" in alice_memories.json()["content"]


def test_dialogue_memory_extracts_from_question_only(client):
    response = client.post(
        "/api/dialogue-memories",
        json={"ldapId": "question-only-001", "question": "我是李玉，今年35岁"},
    )
    assert response.status_code == 200
    assert response.json()["saved"] >= 1

    memories = client.get("/api/dialogue-memories/question-only-001")
    assert memories.status_code == 200
    assert "个人记忆汇总" in memories.json()["content"]
    assert "李玉" in memories.json()["content"] or "35" in memories.json()["content"]
    assert memories.json()["content"].count("李玉") == 1


def test_dialogue_memory_writes_markdown_files(client):
    client.post(
        "/api/dialogue-memories",
        json={"ldapId": "md001", "question": "remember: I am in finance department and prefer direct conclusions."},
    )
    admin_token = token(client, "admin", "admin123")
    markdown = client.get(
        "/api/admin/memories/md001/markdown",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert markdown.status_code == 200
    payload = markdown.json()
    assert set(payload) == {"profile", "long_term", "temporary"}
    assert "md001" in payload["profile"]["content"]


def test_memory_layers_and_admin_crud(client):
    client.post(
        "/api/dialogue-memories",
        json={"ldapId": "alice001", "question": "I am in sales department. temporary today: prepare quarterly review."},
    )
    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}
    profile = client.get("/api/admin/memories/alice001?layer=profile", headers=headers)
    assert profile.status_code == 200
    assert len(profile.json()) >= 1

    memory = profile.json()[0]
    updated = client.patch(
        f"/api/admin/memories/alice001/{memory['id']}",
        json={"content": "李玉在销售部。", "layer": "profile", "status": "inactive"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    deleted = client.delete(f"/api/admin/memories/alice001/{memory['id']}", headers=headers)
    assert deleted.status_code == 200


def test_dialogue_memory_accepts_legacy_ai_reply_for_compatibility(client):
    response = client.post(
        "/api/dialogue-memories",
        json={
            "ldapId": "legacy-ai-reply-001",
            "question": "remember: I prefer concise summaries.",
            "aiReply": "Legacy callers may still send this field.",
        },
    )
    assert response.status_code == 200
    assert response.json()["saved"] >= 1


def test_temporary_memories_are_returned_as_single_recent_markdown_summary(client):
    for text in [
        "temporary today: focus on the quarterly review deck.",
        "temporary current task: prepare API rollout notes.",
    ]:
        response = client.post(
            "/api/dialogue-memories",
            json={"ldapId": "temp-summary-001", "question": text},
        )
        assert response.status_code == 200

    memories = client.get("/api/dialogue-memories/temp-summary-001?layer=temporary")
    assert memories.status_code == 200
    payload = memories.json()
    assert payload["ldapId"] == "temp-summary-001"
    assert "临时记忆" in payload["content"]
    assert "quarterly review deck" in payload["content"]
    assert "API rollout notes" in payload["content"]
    assert "temporary_summary" not in payload["content"]


def test_expired_temporary_sources_are_physically_deleted_without_touching_long_term(client):
    client.post(
        "/api/dialogue-memories",
        json={"ldapId": "temp-expire-001", "question": "temporary today: track launch checklist."},
    )
    old_time = datetime.now(timezone.utc) - timedelta(days=6)
    generator, db = open_test_db_session()
    try:
        user = db.query(User).filter(User.ldap_id == "temp-expire-001").one()
        expired = Memory(
            user_id=user.id,
            content="temporary old task that should be deleted",
            layer=MemoryLayer.temporary.value,
            memory_type="context",
            status=MemoryStatus.active.value,
            confidence=0.8,
            created_at=old_time,
            updated_at=old_time,
        )
        old_long_term = Memory(
            user_id=user.id,
            content="old long term memory must stay",
            layer=MemoryLayer.long_term.value,
            memory_type="preference",
            status=MemoryStatus.active.value,
            confidence=0.8,
            created_at=old_time,
            updated_at=old_time,
        )
        db.add_all([expired, old_long_term])
        db.commit()
        expired_id = expired.id
        old_long_term_id = old_long_term.id
    finally:
        generator.close()

    response = client.get("/api/dialogue-memories/temp-expire-001?layer=temporary")
    assert response.status_code == 200
    assert "track launch checklist" in response.json()["content"]

    generator, db = open_test_db_session()
    try:
        assert db.get(Memory, expired_id) is None
        assert db.get(Memory, old_long_term_id) is not None
    finally:
        generator.close()


def test_temporary_markdown_contains_summary_without_expired_sources(client):
    client.post(
        "/api/dialogue-memories",
        json={"ldapId": "temp-md-001", "question": "temporary today: review supplier risk."},
    )
    old_time = datetime.now(timezone.utc) - timedelta(days=6)
    generator, db = open_test_db_session()
    try:
        user = db.query(User).filter(User.ldap_id == "temp-md-001").one()
        db.add(
            Memory(
                user_id=user.id,
                content="temporary expired supplier item",
                layer=MemoryLayer.temporary.value,
                memory_type="context",
                status=MemoryStatus.active.value,
                confidence=0.8,
                created_at=old_time,
                updated_at=old_time,
            )
        )
        db.commit()
    finally:
        generator.close()

    admin_token = token(client, "admin", "admin123")
    markdown = client.get(
        "/api/admin/memories/temp-md-001/markdown",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert markdown.status_code == 200
    temporary = markdown.json()["temporary"]["content"]
    assert "temporary_summary" in temporary
    assert "review supplier risk" in temporary
    assert "expired supplier item" not in temporary


def test_admin_can_create_ldap_user_without_employee_password(client):
    admin_token = token(client, "admin", "admin123")
    created = client.post(
        "/api/users",
        json={"ldap_id": "eve001", "display_name": "Eve", "role": "employee"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert created.status_code == 200
    assert created.json()["ldap_id"] == "eve001"


def test_admin_can_read_and_update_model_config(client):
    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}

    current = client.get("/api/admin/model-config", headers=headers)
    assert current.status_code == 200
    assert current.json()["chat_model"] == "qwen-max"

    updated = client.patch("/api/admin/model-config", json={"chat_model": "qwen-plus"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["chat_model"] == "qwen-plus"


def test_admin_can_manage_model_providers_without_exposing_api_key(client):
    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}

    current = client.get("/api/admin/model-config", headers=headers)
    assert current.status_code == 200
    assert current.json()["chat_model"] == "qwen-max"
    assert current.json()["embedding_model"] == "text-embedding-v4"

    created = client.post(
        "/api/admin/model-providers",
        json={
            "name": "test-provider",
            "base_url": "https://example.test/v1",
            "api_key": "sk-secret-value",
            "chat_model": "test-chat",
            "embedding_model": "test-embedding",
            "protocol": "openai_compatible",
        },
        headers=headers,
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["api_key_configured"] is True
    assert "sk-secret-value" not in str(payload)

    providers = client.get("/api/admin/model-providers", headers=headers)
    assert providers.status_code == 200
    assert any(item["name"] == "test-provider" for item in providers.json())
    assert "sk-secret-value" not in providers.text

    activated = client.post(f"/api/admin/model-providers/{payload['id']}/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["provider_name"] == "test-provider"
    assert activated.json()["chat_model"] == "test-chat"

    delete_current = client.delete(f"/api/admin/model-providers/{payload['id']}", headers=headers)
    assert delete_current.status_code == 400

    default_provider = next(item for item in providers.json() if item["is_default"])
    deleted = client.delete(f"/api/admin/model-providers/{default_provider['id']}", headers=headers)
    assert deleted.status_code == 200


def test_admin_can_test_model_provider_without_api_key(client):
    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/api/admin/model-providers",
        json={
            "name": "no-key-provider",
            "base_url": "https://example.test/v1",
            "chat_model": "test-chat",
            "embedding_model": "test-embedding",
            "protocol": "openai_compatible",
        },
        headers=headers,
    )
    assert created.status_code == 200

    tested = client.post(f"/api/admin/model-providers/{created.json()['id']}/test", headers=headers)
    assert tested.status_code == 200
    payload = tested.json()
    assert payload["ok"] is False
    assert payload["chat_ok"] is False
    assert payload["embedding_ok"] is False
    assert "API Key" in payload["message"]


def test_personal_memory_api_requires_valid_external_token(client):
    missing = client.get("/api/personal/memories")
    assert missing.status_code == 401

    invalid = client.get("/api/personal/memories", headers={"token": "not-a-jwt"})
    assert invalid.status_code == 401

    no_audience = client.get("/api/personal/memories", headers={"token": external_token("alice001", "")})
    assert no_audience.status_code == 401


def test_personal_memory_api_is_scoped_to_token_ldap_id(client):
    alice_headers = {"token": external_token("alice001")}
    bob_headers = {"token": external_token("bob001")}

    created = client.post(
        "/api/personal/memories",
        json={"content": "alice private memory", "layer": "profile", "memory_type": "manual", "status": "active"},
        headers=alice_headers,
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    alice_list = client.get("/api/personal/memories?layer=profile", headers=alice_headers)
    assert alice_list.status_code == 200
    assert any(item["id"] == memory_id for item in alice_list.json())

    bob_update = client.patch(
        f"/api/personal/memories/{memory_id}",
        json={"content": "bob cannot update alice memory"},
        headers=bob_headers,
    )
    assert bob_update.status_code == 404

    updated = client.patch(
        f"/api/personal/memories/{memory_id}",
        json={"content": "alice updated memory"},
        headers=alice_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "alice updated memory"

    deleted = client.delete(f"/api/personal/memories/{memory_id}", headers=alice_headers)
    assert deleted.status_code == 200

    alice_after_delete = client.get("/api/personal/memories?layer=profile", headers=alice_headers)
    assert all(item["id"] != memory_id for item in alice_after_delete.json())
