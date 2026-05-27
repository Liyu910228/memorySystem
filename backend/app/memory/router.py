from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_external_ldap_id, require_admin
from app.memory.service import (
    ensure_user_memory_markdown,
    extract_from_dialogue,
    get_or_create_employee_by_ldap,
    list_memories,
    summarize_temporary_memories,
    sync_user_memory_markdown,
    update_user_memory_markdown_file,
)
from app.shared.database import get_db
from app.shared.llm import embedding
from app.shared.models import Memory, MemoryLayer, MemoryStatus, User
from app.shared.schemas import DialogueMemoryIn, MarkdownUpdate, MemoryCreate, MemoryOut, MemoryUpdate

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
def get_memories(
    q: str | None = None,
    layer: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_memories(db, user.id, q, layer)


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not memory or memory.status == MemoryStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Memory not found")
    was_temporary = memory.layer == MemoryLayer.temporary.value
    if payload.content is not None:
        memory.content = payload.content
        memory.embedding = await embedding(payload.content)
    if payload.layer is not None:
        memory.layer = payload.layer
    if payload.memory_type is not None:
        memory.memory_type = payload.memory_type
    if payload.status is not None:
        memory.status = payload.status
    db.commit()
    db.refresh(memory)
    if was_temporary or memory.layer == MemoryLayer.temporary.value:
        await summarize_temporary_memories(db, user.id)
    sync_user_memory_markdown(db, user)
    return memory


@router.delete("/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memory = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.status = MemoryStatus.deleted.value
    db.commit()
    sync_user_memory_markdown(db, user)
    return {"ok": True}


public_router = APIRouter(prefix="/dialogue-memories", tags=["dialogue-memories"])


def enrich_memory(memory: Memory) -> MemoryOut:
    output = MemoryOut.model_validate(memory)
    output.ldap_id = memory.user.ldap_id if hasattr(memory, "user") and memory.user else None
    return output


@public_router.post("")
async def post_dialogue_memory(payload: DialogueMemoryIn, db: Session = Depends(get_db)):
    user, saved = await extract_from_dialogue(
        db,
        ldap_id=payload.ldapId,
        question=payload.question,
        ai_reply=payload.aiReply,
        display_name=payload.displayName,
    )
    return {"ldapId": user.ldap_id, "saved": saved}


@public_router.get("/{ldap_id}", response_model=list[MemoryOut])
def get_dialogue_memories(
    ldap_id: str,
    layer: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        return []
    return list_memories(db, user.id, q, layer)


admin_router = APIRouter(prefix="/admin/memories", tags=["admin-memories"])
personal_router = APIRouter(prefix="/personal", tags=["personal-memories"])


@personal_router.get("/me")
def personal_me(ldap_id: str = Depends(get_external_ldap_id)):
    return {"ldapId": ldap_id}


@personal_router.get("/memories", response_model=list[MemoryOut])
def personal_get_memories(
    layer: str | None = None,
    q: str | None = None,
    ldap_id: str = Depends(get_external_ldap_id),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        return []
    return list_memories(db, user.id, q, layer)


@personal_router.post("/memories", response_model=MemoryOut)
async def personal_create_memory(
    payload: MemoryCreate,
    ldap_id: str = Depends(get_external_ldap_id),
    db: Session = Depends(get_db),
):
    user = get_or_create_employee_by_ldap(db, ldap_id, payload.display_name)
    memory = Memory(
        user_id=user.id,
        content=payload.content,
        layer=payload.layer,
        memory_type=payload.memory_type,
        status=payload.status,
        confidence=payload.confidence,
        embedding=await embedding(payload.content),
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    if memory.layer == MemoryLayer.temporary.value:
        await summarize_temporary_memories(db, user.id)
    sync_user_memory_markdown(db, user)
    return memory


@personal_router.patch("/memories/{memory_id}", response_model=MemoryOut)
async def personal_update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    ldap_id: str = Depends(get_external_ldap_id),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not memory or memory.status == MemoryStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Memory not found")
    was_temporary = memory.layer == MemoryLayer.temporary.value
    if payload.content is not None:
        memory.content = payload.content
        memory.embedding = await embedding(payload.content)
    if payload.layer is not None:
        memory.layer = payload.layer
    if payload.memory_type is not None:
        memory.memory_type = payload.memory_type
    if payload.status is not None:
        memory.status = payload.status
    db.commit()
    db.refresh(memory)
    if was_temporary or memory.layer == MemoryLayer.temporary.value:
        await summarize_temporary_memories(db, user.id)
    sync_user_memory_markdown(db, user)
    return memory


@personal_router.delete("/memories/{memory_id}")
def personal_delete_memory(
    memory_id: int,
    ldap_id: str = Depends(get_external_ldap_id),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.status = MemoryStatus.deleted.value
    db.commit()
    sync_user_memory_markdown(db, user)
    return {"ok": True}


@admin_router.get("/{ldap_id}", response_model=list[MemoryOut])
def admin_get_user_memories(
    ldap_id: str,
    layer: str | None = None,
    q: str | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        return []
    return list_memories(db, user.id, q, layer)


@admin_router.post("/{ldap_id}", response_model=MemoryOut)
async def admin_create_memory(
    ldap_id: str,
    payload: MemoryCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = get_or_create_employee_by_ldap(db, ldap_id, payload.display_name)
    memory = Memory(
        user_id=user.id,
        content=payload.content,
        layer=payload.layer,
        memory_type=payload.memory_type,
        status=payload.status,
        confidence=payload.confidence,
        embedding=await embedding(payload.content),
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    if memory.layer == MemoryLayer.temporary.value:
        await summarize_temporary_memories(db, user.id)
    sync_user_memory_markdown(db, user)
    return memory


@admin_router.get("/{ldap_id}/markdown")
def admin_get_user_memory_markdown(
    ldap_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    paths = ensure_user_memory_markdown(db, user)
    return {
        layer: {
            "path": path,
            "content": open(path, "r", encoding="utf-8").read(),
        }
        for layer, path in paths.items()
    }


@admin_router.put("/{ldap_id}/markdown/{layer}")
def admin_update_user_memory_markdown(
    ldap_id: str,
    layer: str,
    payload: MarkdownUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    path = update_user_memory_markdown_file(user, layer, payload.content)
    return {
        "layer": layer,
        "path": path,
        "content": open(path, "r", encoding="utf-8").read(),
    }


@admin_router.patch("/{ldap_id}/{memory_id}", response_model=MemoryOut)
async def admin_update_memory(
    ldap_id: str,
    memory_id: int,
    payload: MemoryUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    memory = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not memory or memory.status == MemoryStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Memory not found")
    was_temporary = memory.layer == MemoryLayer.temporary.value
    if payload.content is not None:
        memory.content = payload.content
        memory.embedding = await embedding(payload.content)
    if payload.layer is not None:
        memory.layer = payload.layer
    if payload.memory_type is not None:
        memory.memory_type = payload.memory_type
    if payload.status is not None:
        memory.status = payload.status
    db.commit()
    db.refresh(memory)
    if was_temporary or memory.layer == MemoryLayer.temporary.value:
        await summarize_temporary_memories(db, user.id)
    sync_user_memory_markdown(db, user)
    return memory


@admin_router.delete("/{ldap_id}/{memory_id}")
def admin_delete_memory(
    ldap_id: str,
    memory_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.ldap_id == ldap_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    memory = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.status = MemoryStatus.deleted.value
    db.commit()
    sync_user_memory_markdown(db, user)
    return {"ok": True}
