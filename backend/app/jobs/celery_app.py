from celery import Celery

from app.shared.config import get_settings

settings = get_settings()
celery_app = Celery("personal_memory_ai", broker=settings.redis_url, backend=settings.redis_url)

