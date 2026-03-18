from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from cdx_proxy_cli_v2.auth.rotation import CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE

CHATGPT_ACCOUNT_MODELS = (
    "gpt-5.1-codex-max",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
)
CHATGPT_ACCOUNT_MODEL_FALLBACK = CHATGPT_ACCOUNT_MODELS[0]
CHATGPT_ACCOUNT_MODEL_REWRITES = {
    "gpt-5.4": CHATGPT_ACCOUNT_MODEL_FALLBACK,
    "gpt-5.3-codex": CHATGPT_ACCOUNT_MODEL_FALLBACK,
    "gpt-5.2-codex": CHATGPT_ACCOUNT_MODEL_FALLBACK,
}
CHATGPT_ACCOUNT_MODEL_VERBOSITY = {
    "gpt-5.1-codex-max": {
        "default": "medium",
        "supported": {"medium"},
    }
}
CHATGPT_ACCOUNT_INCOMPATIBLE_MARKERS = (
    "not supported when using codex with a chatgpt account",
    "not supported for codex with a chatgpt account",
)
VALID_REASONING_LEVELS = {"none", "minimal", "low", "medium", "high", "xhigh"}
REASONING_LEVEL_ALIASES = {
    "standard": "medium",
    "extended": "high",
}


def _extract_error_strings(raw_body: bytes) -> list[str]:
    if not raw_body:
        return []
    try:
        parsed = json.loads(raw_body.decode("utf-8", errors="replace"))
    except Exception:
        return []
    texts: list[str] = []
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            for key in ("code", "message", "detail", "type"):
                value = error.get(key)
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
        elif isinstance(error, str) and error.strip():
            texts.append(error.strip())
        for key in ("code", "message", "detail"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    return texts


def _extract_error_code(
    raw_body: bytes, *, status: Optional[int] = None
) -> Optional[str]:
    texts = _extract_error_strings(raw_body)
    if int(status or 0) == 400:
        haystack = " ".join(texts).lower()
        if any(marker in haystack for marker in CHATGPT_ACCOUNT_INCOMPATIBLE_MARKERS):
            return CHATGPT_ACCOUNT_INCOMPATIBLE_ERROR_CODE
    for value in texts:
        if value and " " not in value:
            return value
    return None


def _header_value_case_insensitive(headers: Dict[str, str], key: str) -> str:
    for existing_key, value in headers.items():
        if existing_key.lower() == key.lower():
            return str(value)
    return ""


def _normalize_model_identifier(value: Any) -> str:
    return str(value or "").strip().lower()


def _chatgpt_effective_model(model_name: Any) -> str:
    normalized = _normalize_model_identifier(model_name)
    if not normalized:
        return ""
    return CHATGPT_ACCOUNT_MODEL_REWRITES.get(normalized, normalized)


def _chatgpt_default_verbosity(model_name: Any, *, default: str = "low") -> str:
    effective_model = _chatgpt_effective_model(model_name)
    config = CHATGPT_ACCOUNT_MODEL_VERBOSITY.get(effective_model)
    if not isinstance(config, dict):
        return default
    normalized = str(config.get("default") or "").strip().lower()
    return normalized or default


def _chatgpt_supported_verbosity(model_name: Any) -> set[str]:
    effective_model = _chatgpt_effective_model(model_name)
    config = CHATGPT_ACCOUNT_MODEL_VERBOSITY.get(effective_model)
    if not isinstance(config, dict):
        return set()
    supported = config.get("supported")
    if not isinstance(supported, set):
        return set()
    return {
        str(candidate).strip().lower()
        for candidate in supported
        if str(candidate).strip()
    }


def _normalize_chatgpt_request_body(body: bytes, headers: Dict[str, str]) -> bytes:
    if not body:
        return body
    if "json" not in _header_value_case_insensitive(headers, "Content-Type").lower():
        return body
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return body
    if not isinstance(payload, dict):
        return body
    model = payload.get("model")
    if not isinstance(model, str):
        return body
    rewritten_model = CHATGPT_ACCOUNT_MODEL_REWRITES.get(model.strip())
    if not rewritten_model:
        return body
    payload["model"] = rewritten_model
    text = payload.get("text")
    if isinstance(text, dict):
        supported_verbosity = _chatgpt_supported_verbosity(rewritten_model)
        raw_verbosity = str(text.get("verbosity") or "").strip().lower()
        if raw_verbosity and supported_verbosity and raw_verbosity not in supported_verbosity:
            text["verbosity"] = _chatgpt_default_verbosity(rewritten_model)
    return json.dumps(payload).encode("utf-8")


def _is_models_request_path(path: str) -> bool:
    path_only = urlsplit(path or "").path.rstrip("/")
    return path_only in {"/models", "/backend-api/models"}


def _normalize_model_shell_type(item: dict[str, Any]) -> str:
    slug = str(item.get("slug") or item.get("id") or "").strip().lower()
    title = str(item.get("title") or item.get("display_name") or "").strip().lower()
    if slug == "gpt-5" or title == "gpt-5":
        return "default"
    return "shell_command"


def _codex_cli_static_model_fields(model_name: Any = None) -> dict[str, Any]:
    return {
        "visibility": "list",
        "supported_in_api": True,
        "priority": 0,
        "availability_nux": None,
        "upgrade": None,
        "base_instructions": "",
        "model_messages": {"instructions_template": ""},
        "supports_reasoning_summaries": True,
        "default_reasoning_summary": "none",
        "support_verbosity": True,
        "default_verbosity": _chatgpt_default_verbosity(model_name),
        "apply_patch_tool_type": "freeform",
        "web_search_tool_type": "text_and_image",
        "truncation_policy": {"mode": "tokens", "limit": 10000},
        "supports_parallel_tool_calls": True,
        "supports_image_detail_original": True,
        "effective_context_window_percent": 95,
        "experimental_supported_tools": [],
        "prefer_websockets": True,
    }


def _normalize_model_input_modalities(item: dict[str, Any]) -> list[str]:
    product_features = item.get("product_features")
    if isinstance(product_features, dict):
        attachments = product_features.get("attachments")
        if isinstance(attachments, dict):
            image_mime_types = attachments.get("image_mime_types")
            if isinstance(image_mime_types, list) and image_mime_types:
                return ["text", "image"]
    return ["text"]


def _normalize_model_context_window(item: dict[str, Any]) -> int:
    for key in ("context_window", "max_tokens"):
        raw = item.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 128000


def _normalize_model_catalog_identifier(item: dict[str, Any]) -> str:
    for key in ("slug", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_reasoning_level(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in VALID_REASONING_LEVELS:
        return raw
    return REASONING_LEVEL_ALIASES.get(raw)


def _normalize_model_default_reasoning_level(item: dict[str, Any]) -> str:
    normalized_existing = _normalize_reasoning_level(item.get("default_reasoning_level"))
    if normalized_existing:
        return normalized_existing
    supported = item.get("supported_reasoning_levels")
    if isinstance(supported, list):
        for candidate in supported:
            if isinstance(candidate, str) and candidate.strip():
                normalized = _normalize_reasoning_level(candidate)
                if normalized:
                    return normalized
            if isinstance(candidate, dict):
                effort = candidate.get("effort") or candidate.get("thinking_effort")
                normalized = _normalize_reasoning_level(effort)
                if normalized:
                    return normalized
    if str(item.get("reasoning_type") or "").strip().lower() == "reasoning":
        return "medium"
    return "low"


def _normalize_model_supported_reasoning_levels(item: dict[str, Any]) -> list[dict[str, str]]:
    existing = item.get("supported_reasoning_levels")
    normalized: list[dict[str, str]] = []
    seen_efforts: set[str] = set()
    if isinstance(existing, list):
        for candidate in existing:
            if isinstance(candidate, dict):
                effort = candidate.get("effort") or candidate.get("thinking_effort")
                description = candidate.get("description")
                normalized_effort = _normalize_reasoning_level(effort)
                if normalized_effort and normalized_effort not in seen_efforts:
                    normalized.append(
                        {
                            "effort": normalized_effort,
                            "description": str(description or "").strip(),
                        }
                    )
                    seen_efforts.add(normalized_effort)
            elif isinstance(candidate, str) and candidate.strip():
                normalized_effort = _normalize_reasoning_level(candidate)
                if normalized_effort and normalized_effort not in seen_efforts:
                    normalized.append(
                        {
                            "effort": normalized_effort,
                            "description": candidate.strip(),
                        }
                    )
                    seen_efforts.add(normalized_effort)
        if normalized:
            return normalized

    thinking_efforts = item.get("thinking_efforts")
    if not isinstance(thinking_efforts, list):
        return []
    for effort in thinking_efforts:
        if not isinstance(effort, dict):
            continue
        effort_name = effort.get("thinking_effort")
        normalized_effort = _normalize_reasoning_level(effort_name)
        if not normalized_effort or normalized_effort in seen_efforts:
            continue
        description = (
            effort.get("description")
            or effort.get("full_label")
            or effort.get("mobile_full_label")
            or effort.get("short_label")
            or effort_name
        )
        normalized.append(
            {
                "effort": normalized_effort,
                "description": str(description).strip(),
            }
        )
        seen_efforts.add(normalized_effort)
    return normalized


def _normalize_codex_cli_model_fields(item: dict[str, Any]) -> bool:
    changed = False
    model_name = _normalize_model_catalog_identifier(item)

    def ensure(key: str, value: Any) -> None:
        nonlocal changed
        if key in item:
            return
        item[key] = value
        changed = True

    for key, value in _codex_cli_static_model_fields(model_name).items():
        ensure(key, value)

    normalized_default_verbosity = _chatgpt_default_verbosity(model_name)
    if item.get("default_verbosity") != normalized_default_verbosity:
        item["default_verbosity"] = normalized_default_verbosity
        changed = True

    normalized_default_reasoning_level = _normalize_model_default_reasoning_level(item)
    if item.get("default_reasoning_level") != normalized_default_reasoning_level:
        item["default_reasoning_level"] = normalized_default_reasoning_level
        changed = True
    if "context_window" not in item:
        item["context_window"] = _normalize_model_context_window(item)
        changed = True
    if "input_modalities" not in item:
        item["input_modalities"] = _normalize_model_input_modalities(item)
        changed = True

    return changed


def _normalize_models_response_body(body: bytes, *, request_path: str) -> bytes:
    if not body or not _is_models_request_path(request_path):
        return body
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return body
    changed = False
    if isinstance(payload, dict):
        for key in ("models", "data"):
            models = payload.get(key)
            if not isinstance(models, list):
                continue
            for item in models:
                if not isinstance(item, dict):
                    continue
                if not item.get("display_name"):
                    display_name = (
                        item.get("title") or item.get("slug") or item.get("id")
                    )
                    if isinstance(display_name, str) and display_name.strip():
                        item["display_name"] = display_name
                        changed = True
                normalized_reasoning_levels = (
                    _normalize_model_supported_reasoning_levels(item)
                )
                if item.get("supported_reasoning_levels") != normalized_reasoning_levels:
                    item["supported_reasoning_levels"] = normalized_reasoning_levels
                    changed = True
                if (
                    not isinstance(item.get("shell_type"), str)
                    or not str(item.get("shell_type") or "").strip()
                ):
                    item["shell_type"] = _normalize_model_shell_type(item)
                    changed = True
                if _normalize_codex_cli_model_fields(item):
                    changed = True
    if not changed:
        return body
    return json.dumps(payload).encode("utf-8")
