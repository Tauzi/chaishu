from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from prompts import CHARACTER_PROMPT, OUTLINE_PROMPT


DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


def models_url_from_chat_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url.strip())
    if parsed.path.endswith("/chat/completions"):
        path = parsed.path[: -len("/chat/completions")] + "/models"
    else:
        path = "/v1/models"
    return urllib.parse.urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def api_request(url: str, api_key: str, payload: dict | None = None, timeout: int = 120) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"API 请求失败：{exc.code}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络请求失败：{exc.reason}") from exc


def fetch_models(api_key: str, base_url: str) -> list[str]:
    result = api_request(models_url_from_chat_url(base_url), api_key, timeout=60)
    return sorted(item.get("id", "") for item in result.get("data", []) if item.get("id"))


def chat_content(api_key: str, base_url: str, model: str, system: str, user: str, temperature: float) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
    }
    result = api_request(base_url, api_key, payload)
    try:
        return result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"API 返回格式异常：{result}") from exc


def call_outline(api_key: str, base_url: str, model: str, title: str, text: str, context: str) -> str:
    return chat_content(
        api_key,
        base_url,
        model,
        "你是专业网文拆书编辑，必须保持前后章节设定一致，只输出用户要求的 Markdown。",
        OUTLINE_PROMPT.format(title=title, text=text, context=context or "暂无上下文，这是第一章或独立分块。"),
        0.25,
    )


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"角色信息不是有效 JSON：{text[:300]}")
    return json.loads(cleaned[start : end + 1])


def update_character_registry(
    api_key: str,
    base_url: str,
    model: str,
    registry: dict,
    title: str,
    text: str,
    context: str,
) -> dict:
    prompt = CHARACTER_PROMPT.format(
        registry=json.dumps(registry, ensure_ascii=False, indent=2),
        title=title,
        text=text,
        context=context or "暂无上下文。",
    )
    content = chat_content(api_key, base_url, model, "你是小说角色档案整理助手，只输出合法 JSON。", prompt, 0.1)
    return extract_json_object(content)
