import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.shared.database import get_db
from app.shared.model_config import (
    get_current_provider,
    provider_to_config_out,
    provider_to_out,
    update_runtime_model_config,
)
from app.shared.models import ModelProvider, User
from app.shared.schemas import (
    ModelConfigOut,
    ModelConfigUpdate,
    ModelProviderCreate,
    ModelProviderOut,
    ModelProviderTestOut,
    ModelProviderUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/model-config", response_model=ModelConfigOut)
def get_model_config(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return provider_to_config_out(get_current_provider(db))


@router.patch("/model-config", response_model=ModelConfigOut)
def update_model_config(
    payload: ModelConfigUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = update_runtime_model_config(
        db,
        base_url=payload.base_url,
        chat_model=payload.chat_model,
        embedding_model=payload.embedding_model,
    )
    provider = get_current_provider(db)
    provider.base_url = config.base_url
    provider.chat_model = config.chat_model
    provider.embedding_model = config.embedding_model
    return provider_to_config_out(provider)


@router.get("/model-providers", response_model=list[ModelProviderOut])
def list_model_providers(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    get_current_provider(db)
    providers = db.scalars(
        select(ModelProvider).order_by(ModelProvider.is_default.desc(), ModelProvider.created_at.asc(), ModelProvider.id.asc())
    ).all()
    return [provider_to_out(provider) for provider in providers]


@router.post("/model-providers", response_model=ModelProviderOut)
def create_model_provider(
    payload: ModelProviderCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    has_provider = db.scalar(select(ModelProvider.id).limit(1)) is not None
    provider = ModelProvider(
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key or None,
        chat_model=payload.chat_model,
        embedding_model=payload.embedding_model,
        protocol=payload.protocol,
        is_enabled=payload.is_enabled,
        is_default=not has_provider,
    )
    db.add(provider)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="供应商名称已存在") from exc
    db.refresh(provider)
    return provider_to_out(provider)


@router.patch("/model-providers/{provider_id}", response_model=ModelProviderOut)
def update_model_provider(
    provider_id: int,
    payload: ModelProviderUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = db.get(ModelProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")

    changes = payload.model_dump(exclude_unset=True)
    for field in ("name", "base_url", "chat_model", "embedding_model", "protocol", "is_enabled"):
        if field in changes:
            setattr(provider, field, changes[field])
    if "api_key" in changes and changes["api_key"] is not None:
        provider.api_key = changes["api_key"] or None

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="供应商名称已存在") from exc
    db.refresh(provider)
    return provider_to_out(provider)


@router.post("/model-providers/{provider_id}/activate", response_model=ModelConfigOut)
def activate_model_provider(
    provider_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = db.get(ModelProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if not provider.is_enabled:
        raise HTTPException(status_code=400, detail="不能启用已停用供应商")

    for item in db.scalars(select(ModelProvider)).all():
        item.is_default = item.id == provider.id
    db.commit()
    db.refresh(provider)
    return provider_to_config_out(provider)


@router.post("/model-providers/{provider_id}/test", response_model=ModelProviderTestOut)
async def test_model_provider(
    provider_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = db.get(ModelProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if not provider.api_key:
        return ModelProviderTestOut(
            provider_id=provider.id,
            provider_name=provider.name,
            ok=False,
            chat_ok=False,
            embedding_ok=False,
            latency_ms=0,
            message="API Key 未配置，无法测试真实模型",
        )

    started = time.perf_counter()
    chat_ok = False
    embedding_ok = False
    errors: list[str] = []
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    base_url = provider.base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=25) as client:
        try:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": provider.chat_model,
                    "messages": [
                        {"role": "system", "content": "你是模型连通性测试助手。"},
                        {"role": "user", "content": "请只回复 OK"},
                    ],
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            chat_ok = bool(str(content).strip())
        except (KeyError, IndexError, TypeError, httpx.HTTPError) as exc:
            errors.append(f"聊天模型失败：{exc}")

        try:
            response = await client.post(
                f"{base_url}/embeddings",
                headers=headers,
                json={"model": provider.embedding_model, "input": "model connectivity test"},
            )
            response.raise_for_status()
            embedding = response.json()["data"][0]["embedding"]
            embedding_ok = isinstance(embedding, list) and len(embedding) > 0
            if not embedding_ok:
                errors.append("向量模型失败：响应中没有 embedding")
        except (KeyError, IndexError, TypeError, httpx.HTTPError) as exc:
            errors.append(f"向量模型失败：{exc}")

    latency_ms = int((time.perf_counter() - started) * 1000)
    ok = chat_ok and embedding_ok
    return ModelProviderTestOut(
        provider_id=provider.id,
        provider_name=provider.name,
        ok=ok,
        chat_ok=chat_ok,
        embedding_ok=embedding_ok,
        latency_ms=latency_ms,
        message="模型测试通过" if ok else "；".join(errors),
    )


@router.delete("/model-providers/{provider_id}")
def delete_model_provider(
    provider_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    provider = db.get(ModelProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    if provider.is_default:
        raise HTTPException(status_code=400, detail="当前供应商不可删除")

    db.delete(provider)
    db.commit()
    return {"deleted": True}
