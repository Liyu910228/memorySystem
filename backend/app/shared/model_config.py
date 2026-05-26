from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.shared.config import get_settings
from app.shared.database import SessionLocal
from app.shared.models import ModelProtocol, ModelProvider
from app.shared.schemas import ModelConfigOut, ModelProviderOut


class RuntimeModelConfig(BaseModel):
    provider_id: int | None = None
    provider_name: str = "Default"
    base_url: str
    api_key: str = ""
    chat_model: str
    embedding_model: str
    protocol: str = ModelProtocol.openai_compatible.value


settings = get_settings()


def api_key_hint(api_key: str | None) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "已配置"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _env_runtime_config() -> RuntimeModelConfig:
    return RuntimeModelConfig(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        chat_model=settings.chat_model,
        embedding_model=settings.embedding_model,
    )


def ensure_default_model_provider(db: Session) -> ModelProvider:
    provider = db.scalar(select(ModelProvider).order_by(ModelProvider.is_default.desc(), ModelProvider.id.asc()).limit(1))
    if provider:
        return provider

    provider = ModelProvider(
        name="默认供应商",
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key or None,
        chat_model=settings.chat_model,
        embedding_model=settings.embedding_model,
        protocol=ModelProtocol.openai_compatible.value,
        is_enabled=True,
        is_default=True,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def get_current_provider(db: Session) -> ModelProvider:
    ensure_default_model_provider(db)
    provider = db.scalar(
        select(ModelProvider)
        .where(ModelProvider.is_default.is_(True), ModelProvider.is_enabled.is_(True))
        .order_by(ModelProvider.id.asc())
        .limit(1)
    )
    if provider:
        return provider

    provider = db.scalar(
        select(ModelProvider).where(ModelProvider.is_enabled.is_(True)).order_by(ModelProvider.id.asc()).limit(1)
    )
    if provider:
        provider.is_default = True
        db.commit()
        db.refresh(provider)
        return provider

    provider = ensure_default_model_provider(db)
    provider.is_enabled = True
    provider.is_default = True
    db.commit()
    db.refresh(provider)
    return provider


def provider_to_runtime(provider: ModelProvider) -> RuntimeModelConfig:
    return RuntimeModelConfig(
        provider_id=provider.id,
        provider_name=provider.name,
        base_url=provider.base_url,
        api_key=provider.api_key or "",
        chat_model=provider.chat_model,
        embedding_model=provider.embedding_model,
        protocol=provider.protocol,
    )


def provider_to_config_out(provider: ModelProvider) -> ModelConfigOut:
    return ModelConfigOut(
        provider_id=provider.id,
        provider_name=provider.name,
        base_url=provider.base_url,
        chat_model=provider.chat_model,
        embedding_model=provider.embedding_model,
        protocol=provider.protocol,
        api_key_configured=bool(provider.api_key),
        api_key_hint=api_key_hint(provider.api_key),
    )


def provider_to_out(provider: ModelProvider) -> ModelProviderOut:
    return ModelProviderOut(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        chat_model=provider.chat_model,
        embedding_model=provider.embedding_model,
        protocol=provider.protocol,
        is_enabled=provider.is_enabled,
        is_default=provider.is_default,
        api_key_configured=bool(provider.api_key),
        api_key_hint=api_key_hint(provider.api_key),
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def get_runtime_model_config(db: Session | None = None) -> RuntimeModelConfig:
    if db is not None:
        return provider_to_runtime(get_current_provider(db))

    with SessionLocal() as session:
        try:
            return provider_to_runtime(get_current_provider(session))
        except SQLAlchemyError:
            return _env_runtime_config()


def update_runtime_model_config(
    db: Session,
    chat_model: str | None = None,
    base_url: str | None = None,
    embedding_model: str | None = None,
) -> RuntimeModelConfig:
    provider = get_current_provider(db)
    if base_url is not None:
        provider.base_url = base_url
    if chat_model is not None:
        provider.chat_model = chat_model
    if embedding_model is not None:
        provider.embedding_model = embedding_model
    db.commit()
    db.refresh(provider)
    return provider_to_runtime(provider)
