from tests.conftest import token
from jose import jwt


def external_token(ldap_id: str, audience_field: str = "aud") -> str:
    payload = {audience_field: ldap_id} if audience_field else {"sub": ldap_id}
    return jwt.encode(payload, "external-secret", algorithm="HS256")


def test_dialogue_memory_isolated_by_ldap_id(client):
    alice = client.post(
        "/api/dialogue-memories",
        json={
            "ldapId": "alice001",
            "question": "记住，我喜欢用中文回答和简洁摘要。",
            "aiReply": "好的，我会记住你的回答偏好。",
        },
    )
    assert alice.status_code == 200
    assert alice.json()["saved"] >= 1

    bob = client.get("/api/dialogue-memories/bob001")
    alice_memories = client.get("/api/dialogue-memories/alice001")
    assert bob.status_code == 200
    assert bob.json() == []
    assert len(alice_memories.json()) >= 1


def test_dialogue_memory_extracts_from_question_only(client):
    response = client.post(
        "/api/dialogue-memories",
        json={
            "ldapId": "question-only-001",
            "question": "我的名字叫李玉，我喜欢直接给结论。",
        },
    )
    assert response.status_code == 200
    assert response.json()["saved"] >= 1

    memories = client.get("/api/dialogue-memories/question-only-001")
    assert memories.status_code == 200
    assert any("李玉" in item["content"] for item in memories.json())


def test_dialogue_memory_writes_markdown_files(client):
    client.post(
        "/api/dialogue-memories",
        json={
            "ldapId": "md001",
            "question": "remember: I am in finance department and prefer direct conclusions.",
            "aiReply": "OK, I will remember your profile and preference.",
        },
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
        json={
            "ldapId": "alice001",
            "question": "我是销售部的李雷，今天临时要准备季度复盘。",
            "aiReply": "我会在后续回答中结合你的身份和当前任务。",
        },
    )
    profile = client.get("/api/dialogue-memories/alice001?layer=profile")
    assert profile.status_code == 200
    assert len(profile.json()) >= 1

    admin_token = token(client, "admin", "admin123")
    memory = profile.json()[0]
    updated = client.patch(
        f"/api/admin/memories/alice001/{memory['id']}",
        json={"content": "李雷在销售部。", "layer": "profile", "status": "inactive"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    deleted = client.delete(
        f"/api/admin/memories/alice001/{memory['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deleted.status_code == 200


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

    updated = client.patch(
        "/api/admin/model-config",
        json={"chat_model": "qwen-plus"},
        headers=headers,
    )
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
        json={"content": "alice 私人记忆", "layer": "profile", "memory_type": "manual", "status": "active"},
        headers=alice_headers,
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    alice_list = client.get("/api/personal/memories?layer=profile", headers=alice_headers)
    assert alice_list.status_code == 200
    assert any(item["id"] == memory_id for item in alice_list.json())

    bob_update = client.patch(
        f"/api/personal/memories/{memory_id}",
        json={"content": "bob 不能改 alice 的记忆"},
        headers=bob_headers,
    )
    assert bob_update.status_code == 404

    updated = client.patch(
        f"/api/personal/memories/{memory_id}",
        json={"content": "alice 已更新记忆"},
        headers=alice_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "alice 已更新记忆"

    deleted = client.delete(f"/api/personal/memories/{memory_id}", headers=alice_headers)
    assert deleted.status_code == 200

    alice_after_delete = client.get("/api/personal/memories?layer=profile", headers=alice_headers)
    assert all(item["id"] != memory_id for item in alice_after_delete.json())
