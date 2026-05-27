import asyncio
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.shared.config import get_settings
from app.shared.llm import chat_completion, cosine_similarity, embedding, extract_memories
from app.shared.model_config import get_runtime_model_config
from app.shared.models import Memory, MemoryLayer, MemoryStatus, Message, Role, User, now_utc

settings = get_settings()
TEMPORARY_MEMORY_DAYS = 5
TEMPORARY_SUMMARY_TYPE = "temporary_summary"

LAYER_FILES = {
    MemoryLayer.profile.value: ("profile.md", "个人基本信息"),
    MemoryLayer.long_term.value: ("long_term.md", "长期记忆"),
    MemoryLayer.temporary.value: ("temporary.md", "临时记忆"),
}


def normalize_layer(layer: str | None) -> str:
    valid = {item.value for item in MemoryLayer}
    return layer if layer in valid else MemoryLayer.long_term.value


def temporary_memory_cutoff():
    return now_utc() - timedelta(days=TEMPORARY_MEMORY_DAYS)


def is_temporary_summary(memory: Memory) -> bool:
    return memory.layer == MemoryLayer.temporary.value and memory.memory_type == TEMPORARY_SUMMARY_TYPE


def cleanup_expired_temporary_memories(db: Session, user_id: int) -> int:
    result = db.execute(
        delete(Memory).where(
            Memory.user_id == user_id,
            Memory.layer == MemoryLayer.temporary.value,
            Memory.memory_type != TEMPORARY_SUMMARY_TYPE,
            Memory.updated_at < temporary_memory_cutoff(),
        )
    )
    return int(result.rowcount or 0)


def recent_temporary_memory_sources(db: Session, user_id: int) -> list[Memory]:
    return list(
        db.scalars(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.layer == MemoryLayer.temporary.value,
                Memory.memory_type != TEMPORARY_SUMMARY_TYPE,
                Memory.status != MemoryStatus.deleted.value,
                Memory.updated_at >= temporary_memory_cutoff(),
            )
            .order_by(Memory.updated_at.desc())
        )
    )


def get_temporary_summary_memory(db: Session, user_id: int) -> Memory | None:
    return db.scalar(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.layer == MemoryLayer.temporary.value,
            Memory.memory_type == TEMPORARY_SUMMARY_TYPE,
            Memory.status != MemoryStatus.deleted.value,
        )
    )


def fallback_temporary_summary(memories: list[Memory]) -> str:
    snippets: list[str] = []
    seen: set[str] = set()
    for memory in memories:
        text = re.sub(r"\s+", " ", memory.content).strip()
        text = re.sub(r"^(user|assistant|system):\s*", "", text, flags=re.IGNORECASE)
        if not text or text in seen:
            continue
        seen.add(text)
        snippets.append(text[:120])
        if len(snippets) >= 5:
            break
    if not snippets:
        return ""
    return f"最近 {TEMPORARY_MEMORY_DAYS} 天关注：" + "；".join(snippets)


async def build_temporary_summary(db: Session, memories: list[Memory]) -> str:
    fallback = fallback_temporary_summary(memories)
    if not fallback or not get_runtime_model_config(db).api_key:
        return fallback

    source_text = "\n".join(f"- {memory.content.strip()}" for memory in memories[:20])
    prompt = (
        "你是个人记忆系统的整理助手。请把用户最近 5 天的临时记忆整理成一条简短中文汇总，"
        "只保留用户最近关注的事项、当前任务、阶段性上下文。不要编造信息，不要超过 120 字。"
    )
    try:
        summary = await chat_completion(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": source_text},
            ]
        )
    except Exception:
        return fallback
    summary = re.sub(r"\s+", " ", summary).strip()
    if summary and not summary.startswith("最近"):
        summary = f"最近 {TEMPORARY_MEMORY_DAYS} 天关注：{summary}"
    return summary[:500] if summary else fallback


def prune_stale_temporary_summary(db: Session, user_id: int) -> None:
    deleted = cleanup_expired_temporary_memories(db, user_id)
    if recent_temporary_memory_sources(db, user_id):
        if deleted:
            db.commit()
        return
    summary = get_temporary_summary_memory(db, user_id)
    if summary:
        db.delete(summary)
    if deleted or summary:
        db.commit()


async def summarize_temporary_memories(db: Session, user_id: int) -> Memory | None:
    cleanup_expired_temporary_memories(db, user_id)
    sources = recent_temporary_memory_sources(db, user_id)
    summary = get_temporary_summary_memory(db, user_id)
    if not sources:
        if summary:
            db.delete(summary)
            db.commit()
        return None

    content = await build_temporary_summary(db, sources)
    if not content:
        return None
    vector = await embedding(content)
    if summary:
        summary.content = content
        summary.confidence = max((memory.confidence for memory in sources), default=0.7)
        summary.status = MemoryStatus.active.value
        summary.embedding = vector
    else:
        summary = Memory(
            user_id=user_id,
            content=content,
            layer=MemoryLayer.temporary.value,
            memory_type=TEMPORARY_SUMMARY_TYPE,
            confidence=max((memory.confidence for memory in sources), default=0.7),
            status=MemoryStatus.active.value,
            embedding=vector,
        )
        db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


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
    normalized_layer = normalize_layer(layer) if layer else None
    if normalized_layer == MemoryLayer.temporary.value or normalized_layer is None:
        prune_stale_temporary_summary(db, user_id)
    stmt = select(Memory).where(Memory.user_id == user_id, Memory.status != MemoryStatus.deleted.value)
    if query:
        stmt = stmt.where(Memory.content.ilike(f"%{query}%"))
    if normalized_layer:
        stmt = stmt.where(Memory.layer == normalized_layer)
        if normalized_layer == MemoryLayer.temporary.value:
            stmt = stmt.where(Memory.memory_type == TEMPORARY_SUMMARY_TYPE)
    else:
        stmt = stmt.where(or_(Memory.layer != MemoryLayer.temporary.value, Memory.memory_type == TEMPORARY_SUMMARY_TYPE))
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
    has_temporary_candidate = False
    for item in candidates:
        content = str(item.get("content", "")).strip()
        if len(content) < 4:
            continue
        layer = normalize_layer(item.get("layer"))
        memory_type = str(item.get("memory_type", "preference"))
        if layer == MemoryLayer.temporary.value:
            has_temporary_candidate = True
        existing = db.scalar(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.status != MemoryStatus.deleted.value,
                Memory.content == content,
                Memory.memory_type != TEMPORARY_SUMMARY_TYPE,
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
                layer=layer,
                memory_type=memory_type,
                confidence=float(item.get("confidence", 0.7)),
                embedding=vector,
            )
        )
        saved += 1
    db.commit()
    if has_temporary_candidate:
        await summarize_temporary_memories(db, user_id)
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
