import asyncio
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.config import get_settings
from app.shared.llm import cosine_similarity, embedding, extract_memories
from app.shared.models import Memory, MemoryLayer, MemoryStatus, Message, Role, User

settings = get_settings()

LAYER_FILES = {
    MemoryLayer.profile.value: ("profile.md", "个人基本信息"),
    MemoryLayer.long_term.value: ("long_term.md", "长期记忆"),
    MemoryLayer.temporary.value: ("temporary.md", "临时记忆"),
}


def normalize_layer(layer: str | None) -> str:
    valid = {item.value for item in MemoryLayer}
    return layer if layer in valid else MemoryLayer.long_term.value


def safe_ldap_path(ldap_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@-]", "_", ldap_id.strip())


def memory_export_path(user: User, layer: str) -> Path:
    ldap_id = user.ldap_id or user.username
    filename = LAYER_FILES[normalize_layer(layer)][0]
    return Path(settings.memory_export_dir) / safe_ldap_path(ldap_id) / filename


def render_layer_markdown(user: User, layer: str, memories: list[Memory]) -> str:
    layer = normalize_layer(layer)
    title = LAYER_FILES[layer][1]
    ldap_id = user.ldap_id or user.username
    lines = [
        f"# {title}",
        "",
        f"- ldapId: `{ldap_id}`",
        f"- 用户显示名: {user.display_name}",
        f"- 记忆层级: `{layer}`",
        f"- 记录数: {len(memories)}",
        "",
        "> 此文件由系统自动生成。建议通过管理页面或管理 API 修改记忆，避免手工编辑后被下一次同步覆盖。",
        "",
    ]
    if not memories:
        lines.extend(["暂无记忆。", ""])
        return "\n".join(lines)

    for memory in memories:
        lines.extend(
            [
                f"## 记忆 #{memory.id}",
                "",
                f"- 状态: `{memory.status}`",
                f"- 类型: `{memory.memory_type}`",
                f"- 置信度: `{memory.confidence:.2f}`",
                f"- 创建时间: {memory.created_at.isoformat()}",
                f"- 更新时间: {memory.updated_at.isoformat()}",
                "",
                memory.content.strip(),
                "",
            ]
        )
    return "\n".join(lines)


def sync_user_memory_markdown(db: Session, user: User) -> dict[str, str]:
    export_root = Path(settings.memory_export_dir) / safe_ldap_path(user.ldap_id or user.username)
    export_root.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for layer, (filename, _) in LAYER_FILES.items():
        memories = list_memories(db, user.id, layer=layer)
        path = export_root / filename
        path.write_text(render_layer_markdown(user, layer, memories), encoding="utf-8")
        written[layer] = str(path)
    return written


def ensure_user_memory_markdown(db: Session, user: User) -> dict[str, str]:
    paths = {layer: memory_export_path(user, layer) for layer in LAYER_FILES}
    if any(not path.exists() for path in paths.values()):
        return sync_user_memory_markdown(db, user)
    return {layer: str(path) for layer, path in paths.items()}


def update_user_memory_markdown_file(user: User, layer: str, content: str) -> str:
    normalized_layer = normalize_layer(layer)
    path = memory_export_path(user, normalized_layer)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def list_memories(db: Session, user_id: int, query: str | None = None, layer: str | None = None) -> list[Memory]:
    stmt = select(Memory).where(Memory.user_id == user_id, Memory.status != MemoryStatus.deleted.value)
    if query:
        stmt = stmt.where(Memory.content.ilike(f"%{query}%"))
    if layer:
        stmt = stmt.where(Memory.layer == normalize_layer(layer))
    return list(db.scalars(stmt.order_by(Memory.updated_at.desc())))


def get_or_create_employee_by_ldap(db: Session, ldap_id: str, display_name: str | None = None) -> User:
    cleaned = ldap_id.strip()
    user = db.scalar(select(User).where(User.ldap_id == cleaned))
    if user:
        return user
    user = User(
        username=f"ldap:{cleaned}",
        ldap_id=cleaned,
        display_name=display_name or cleaned,
        password_hash=None,
        role=Role.employee.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def recall_memories(db: Session, user_id: int, text: str, limit: int = 5) -> list[Memory]:
    query_vector = await embedding(text)
    memories = db.scalars(
        select(Memory).where(Memory.user_id == user_id, Memory.status == MemoryStatus.active.value)
    ).all()
    scored = sorted(memories, key=lambda m: cosine_similarity(m.embedding, query_vector), reverse=True)
    return [memory for memory in scored[:limit] if memory.embedding]


async def store_memory_candidates(db: Session, user_id: int, transcript: str, session_id: int | None = None) -> int:
    candidates = await extract_memories(transcript)
    saved = 0
    for item in candidates:
        content = str(item.get("content", "")).strip()
        if len(content) < 4:
            continue
        existing = db.scalar(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.status != MemoryStatus.deleted.value,
                Memory.content == content,
            )
        )
        if existing:
            continue
        vector = await embedding(content)
        db.add(
            Memory(
                user_id=user_id,
                source_session_id=session_id,
                content=content,
                layer=normalize_layer(item.get("layer")),
                memory_type=str(item.get("memory_type", "preference")),
                confidence=float(item.get("confidence", 0.7)),
                embedding=vector,
            )
        )
        saved += 1
    db.commit()
    user = db.get(User, user_id)
    if user:
        sync_user_memory_markdown(db, user)
    return saved


async def extract_and_store_memories(db: Session, user_id: int, session_id: int) -> int:
    messages = db.scalars(
        select(Message)
        .where(Message.user_id == user_id, Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(8)
    ).all()
    transcript = "\n".join(f"{m.role}: {m.content}" for m in reversed(messages))
    return await store_memory_candidates(db, user_id, transcript, session_id)


async def extract_from_dialogue(db: Session, ldap_id: str, question: str, ai_reply: str | None = None, display_name: str | None = None) -> tuple[User, int]:
    user = get_or_create_employee_by_ldap(db, ldap_id, display_name)
    transcript = f"user: {question}"
    saved = await store_memory_candidates(db, user.id, transcript)
    return user, saved


def extract_and_store_memories_sync(db: Session, user_id: int, session_id: int) -> int:
    return asyncio.run(extract_and_store_memories(db, user_id, session_id))
