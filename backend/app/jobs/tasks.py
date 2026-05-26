from app.jobs.celery_app import celery_app
from app.memory.service import extract_and_store_memories_sync
from app.shared.database import SessionLocal


@celery_app.task(name="memory.extract")
def extract_memory_task(user_id: int, session_id: int) -> int:
    db = SessionLocal()
    try:
        return extract_and_store_memories_sync(db, user_id, session_id)
    finally:
        db.close()

