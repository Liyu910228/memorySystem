from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    ldap_id: str | None
    display_name: str
    role: str
    is_active: bool


class UserCreate(BaseModel):
    ldap_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    role: str = "employee"


class SessionCreate(BaseModel):
    title: str = Field(default="新的子会话", min_length=1, max_length=160)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    thread_id: int
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ChatIn(BaseModel):
    session_id: int
    message: str = Field(min_length=1, max_length=12000)


class DialogueMemoryIn(BaseModel):
    ldapId: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=12000)
    aiReply: str | None = Field(default=None, max_length=12000)
    conversationId: str | None = Field(default=None, max_length=160)
    displayName: str | None = Field(default=None, max_length=120)


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ldap_id: str | None = None
    content: str
    layer: str
    memory_type: str
    confidence: float
    status: str
    source_session_id: int | None
    created_at: datetime
    updated_at: datetime


class DialogueMemoryMarkdownOut(BaseModel):
    ldapId: str
    content: str


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=12000)
    layer: str | None = Field(default=None, max_length=40)
    memory_type: str | None = Field(default=None, max_length=60)
    status: str | None = Field(default=None, max_length=30)


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    layer: str = Field(default="long_term", max_length=40)
    memory_type: str = Field(default="manual", max_length=60)
    status: str = Field(default="active", max_length=30)
    confidence: float = Field(default=1.0, ge=0, le=1)
    display_name: str | None = Field(default=None, max_length=120)


class MarkdownUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=200000)


class ModelConfigOut(BaseModel):
    provider_id: int | None = None
    provider_name: str = "Default"
    base_url: str
    chat_model: str
    embedding_model: str
    protocol: str = "openai_compatible"
    api_key_configured: bool
    api_key_hint: str = ""


class ModelConfigUpdate(BaseModel):
    base_url: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None


class ModelProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    chat_model: str
    embedding_model: str
    protocol: str
    is_enabled: bool
    is_default: bool
    api_key_configured: bool
    api_key_hint: str = ""
    created_at: datetime
    updated_at: datetime


class ModelProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=20000)
    chat_model: str = Field(min_length=1, max_length=120)
    embedding_model: str = Field(min_length=1, max_length=120)
    protocol: str = Field(default="openai_compatible", max_length=60)
    is_enabled: bool = True


class ModelProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=20000)
    chat_model: str | None = Field(default=None, min_length=1, max_length=120)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=120)
    protocol: str | None = Field(default=None, max_length=60)
    is_enabled: bool | None = None


class ModelProviderTestOut(BaseModel):
    provider_id: int
    provider_name: str
    ok: bool
    chat_ok: bool
    embedding_ok: bool
    latency_ms: int
    message: str
