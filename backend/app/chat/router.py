import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.memory.service import extract_and_store_memories, recall_memories
from app.shared.database import get_db
from app.shared.llm import chat_completion
from app.shared.models import ChatSession, Message, MessageRole, Thread, User
from app.shared.schemas import ChatIn, MessageOut, SessionCreate, SessionOut

router = APIRouter(prefix="/chat", tags=["chat"])


def ensure_main_thread(db: Session, user_id: int) -> Thread:
    thread = db.scalar(select(Thread).where(Thread.user_id == user_id, Thread.is_main.is_(True)))
    if thread:
        return thread
    thread = Thread(user_id=user_id, title="超级对话", is_main=True)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_main_thread(db, user.id)
    return list(db.scalars(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc())))


@router.post("/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = ensure_main_thread(db, user.id)
    session = ChatSession(user_id=user.id, thread_id=thread.id, title=payload.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return list(db.scalars(select(Message).where(Message.session_id == session_id, Message.user_id == user.id).order_by(Message.created_at)))


@router.post("/stream")
async def stream_chat(payload: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.scalar(select(ChatSession).where(ChatSession.id == payload.session_id, ChatSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.add(Message(user_id=user.id, session_id=session.id, role=MessageRole.user.value, content=payload.message))
    db.commit()

    memories = await recall_memories(db, user.id, payload.message)
    memory_block = "\n".join(f"- {memory.content}" for memory in memories) or "无"
    history = db.scalars(
        select(Message)
        .where(Message.user_id == user.id, Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(12)
    ).all()
    messages = [
        {
            "role": "system",
            "content": (
                "你是员工的公司内 AI 助手。只使用该员工自己的个人记忆，不使用公司共享知识库。"
                f"\n可用个人记忆：\n{memory_block}"
            ),
        }
    ]
    for item in reversed(history):
        messages.append({"role": item.role, "content": item.content})

    answer = await chat_completion(messages)
    db.add(Message(user_id=user.id, session_id=session.id, role=MessageRole.assistant.value, content=answer))
    db.commit()
    await extract_and_store_memories(db, user.id, session.id)

    async def event_stream():
        for line in answer.splitlines() or [answer]:
            yield f"data: {json.dumps({'token': line + chr(10)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

