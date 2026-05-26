import hashlib
import json
import math
import re

import httpx

from app.shared.config import get_settings
from app.shared.model_config import get_runtime_model_config


settings = get_settings()


def _mock_embedding(text: str, dimensions: int = 64) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [((digest[i % len(digest)] / 255) * 2) - 1 for i in range(dimensions)]
    norm = math.sqrt(sum(v * v for v in values)) or 1
    return [v / norm for v in values]


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[i] * right[i] for i in range(size))
    ln = math.sqrt(sum(v * v for v in left[:size])) or 1
    rn = math.sqrt(sum(v * v for v in right[:size])) or 1
    return dot / (ln * rn)


def _heuristic_extract(transcript: str) -> list[dict]:
    lowered = transcript.lower()
    memories: list[dict] = []

    name_match = re.search(r"(?:我的名字叫|我叫)([^，。,.！!？?\n\s]{1,30})", transcript)
    if name_match:
        memories.append({
            "content": f"我的名字叫{name_match.group(1).strip()}",
            "layer": "profile",
            "memory_type": "profile",
            "confidence": 0.9,
        })

    preference_match = re.search(r"(我(?:喜欢|偏好)[^。！!？?\n]{1,80})", transcript)
    if preference_match:
        memories.append({
            "content": preference_match.group(1).strip("，, "),
            "layer": "long_term",
            "memory_type": "preference",
            "confidence": 0.85,
        })

    markers = [
        "我喜欢", "我偏好", "我的", "记住", "以后", "我是", "我叫", "我在", "临时", "今天",
        "remember", "prefer", "preference", "i am", "my name", "department", "temporary", "today",
    ]
    if not any(marker in lowered for marker in markers):
        return memories

    if memories:
        return memories

    layer = "long_term"
    memory_type = "preference"
    if any(marker in lowered for marker in ["我是", "我叫", "我的姓名", "我在", "我的岗位", "部门", "i am", "my name", "department", "profile"]):
        layer = "profile"
        memory_type = "profile"
    elif any(marker in lowered for marker in ["临时", "今天", "这次", "当前", "temporary", "today", "current"]):
        layer = "temporary"
        memory_type = "context"
    fallback = {"content": transcript[-220:], "layer": layer, "memory_type": memory_type, "confidence": 0.55}
    if not any(item["content"] == fallback["content"] for item in memories):
        memories.append(fallback)
    return memories


def _merge_memory_candidates(*candidate_groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for candidates in candidate_groups:
        for item in candidates:
            content = str(item.get("content", "")).strip()
            layer = str(item.get("layer", "long_term"))
            key = (layer, content)
            if not content or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


async def chat_completion(messages: list[dict[str, str]]) -> str:
    model_config = get_runtime_model_config()
    if not model_config.api_key:
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"我已收到：{user_msg}\n\n这是本地 mock 回复。配置 OPENAI_API_KEY 后会调用真实模型。"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{model_config.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {model_config.api_key}"},
            json={"model": model_config.chat_model, "messages": messages, "temperature": 0.3},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def embedding(text: str) -> list[float]:
    model_config = get_runtime_model_config()
    if not model_config.api_key:
        return _mock_embedding(text, min(settings.embedding_dimensions, 64))

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                f"{model_config.base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {model_config.api_key}"},
                json={"model": model_config.embedding_model, "input": text},
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except httpx.HTTPError:
            return _mock_embedding(text, min(settings.embedding_dimensions, 64))


def _parse_json_array(text: str) -> list[dict]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []


async def extract_memories(transcript: str) -> list[dict]:
    rule_candidates = _heuristic_extract(transcript)
    if not get_runtime_model_config().api_key:
        return rule_candidates

    prompt = (
        "从以下员工输入中抽取个人记忆。只返回 JSON 数组，"
        "每项包含 content、layer、memory_type、confidence。不要返回解释文字。"
        "如果一句话里同时包含姓名、部门、偏好、当前任务等多个事实，必须拆成多条记忆，不要合并或遗漏。"
        "content 必须保留关键实体原文，例如姓名、部门、岗位、偏好对象。"
        "layer 只能是 profile、long_term、temporary。"
        "profile 用于姓名、岗位、部门、联系方式等个人基本信息；"
        "long_term 用于长期偏好、工作习惯、稳定背景；"
        "temporary 用于短期上下文、当前任务、阶段性状态。"
    )
    result = await chat_completion([
        {"role": "system", "content": prompt},
        {"role": "user", "content": transcript},
    ])
    parsed = _parse_json_array(result)
    return _merge_memory_candidates(rule_candidates, parsed)
