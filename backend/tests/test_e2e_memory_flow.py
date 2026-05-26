from tests.conftest import token


def test_admin_e2e_memory_flow(client):
    write_response = client.post(
        "/api/dialogue-memories",
        json={
            "ldapId": "e2e001",
            "displayName": "E2E User",
            "question": "记住，我是财务部员工，偏好直接给结论。",
        },
    )
    assert write_response.status_code == 200
    assert write_response.json()["saved"] >= 1

    read_response = client.get("/api/dialogue-memories/e2e001")
    assert read_response.status_code == 200
    memories = read_response.json()
    assert memories

    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}

    markdown_response = client.get("/api/admin/memories/e2e001/markdown", headers=headers)
    assert markdown_response.status_code == 200
    assert "e2e001" in markdown_response.json()["profile"]["content"]

    memory_id = memories[0]["id"]
    update_response = client.patch(
        f"/api/admin/memories/e2e001/{memory_id}",
        json={"content": "该员工偏好直接给结论。", "layer": "long_term", "status": "active"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "该员工偏好直接给结论。"

    delete_response = client.delete(f"/api/admin/memories/e2e001/{memory_id}", headers=headers)
    assert delete_response.status_code == 200

    after_delete = client.get("/api/dialogue-memories/e2e001")
    assert all(item["id"] != memory_id for item in after_delete.json())


def test_admin_can_update_markdown_file_by_ldap_id(client):
    client.post(
        "/api/dialogue-memories",
        json={
            "ldapId": "file-edit-001",
            "question": "记住，我需要能按 ldapId 查询和编辑文件。",
        },
    )
    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}

    markdown = client.get("/api/admin/memories/file-edit-001/markdown", headers=headers)
    assert markdown.status_code == 200

    updated_content = "# 手工编辑\n\n- ldapId: `file-edit-001`\n- 管理员保存成功\n"
    updated = client.put(
        "/api/admin/memories/file-edit-001/markdown/profile",
        json={"content": updated_content},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == updated_content

    reread = client.get("/api/admin/memories/file-edit-001/markdown", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["profile"]["content"] == updated_content


def test_admin_can_create_memory_by_ldap_id(client):
    admin_token = token(client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/api/admin/memories/manual-001",
        json={
            "content": "用户偏好先给结论。",
            "layer": "long_term",
            "memory_type": "manual",
        },
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["content"] == "用户偏好先给结论。"

    memories = client.get("/api/dialogue-memories/manual-001")
    assert memories.status_code == 200
    assert any(item["content"] == "用户偏好先给结论。" for item in memories.json())
