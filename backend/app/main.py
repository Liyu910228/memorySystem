from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.chat.router import ensure_main_thread, router as chat_router
from app.memory.router import admin_router as admin_memory_router
from app.memory.router import public_router as public_memory_router
from app.memory.router import router as memory_router
from app.shared.config import get_settings
from app.shared.database import Base, engine
from app.shared.model_config import ensure_default_model_provider, get_runtime_model_config
from app.shared.models import Role, User
from app.shared.security import hash_password
from app.users.router import router as users_router

settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    if settings.is_production and settings.jwt_secret == "change-me-in-production":
        raise RuntimeError("JWT_SECRET must be changed before starting production")

    if not settings.is_production:
        Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        ensure_default_model_provider(db)
        if not settings.auto_create_admin:
            return

        admin = db.scalar(select(User).where(User.username == settings.admin_username))
        if not admin:
            password = settings.admin_password or ("admin123" if not settings.is_production else "")
            if settings.is_production and (not password or password == "admin123"):
                raise RuntimeError("ADMIN_PASSWORD must be set to a strong non-default value in production")
            admin = User(
                username=settings.admin_username,
                display_name=settings.admin_display_name,
                password_hash=hash_password(password),
                role=Role.admin.value,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            ensure_main_thread(db, admin.id)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "model_configured": bool(get_runtime_model_config().api_key),
    }


app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(public_memory_router, prefix="/api")
app.include_router(admin_memory_router, prefix="/api")
app.include_router(users_router, prefix="/api")
