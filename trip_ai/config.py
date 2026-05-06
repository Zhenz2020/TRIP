from __future__ import annotations

import os
from dataclasses import dataclass


def _get_secret(name: str) -> str | None:
    """
    Streamlit secrets first, then env vars. Keep it tiny to avoid hard dependency
    on Streamlit in non-UI modules.
    """
    try:
        import streamlit as st  # type: ignore

        v = st.secrets.get(name)  # pragma: no cover
        if v:
            return str(v)
    except Exception:
        pass
    v = os.getenv(name)
    return v if v else None


@dataclass(frozen=True)
class Settings:
    paddle_ocr_api_url: str = "https://42n9f1c1u9yci9dd.aistudio-app.com/layout-parsing"
    paddle_ocr_token: str | None = None

    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "Pro/Qwen/Qwen2.5-7B-Instruct"
    siliconflow_vision_model: str = "Qwen/Qwen3.5-27B"
    siliconflow_api_keys: tuple[str, ...] = ()
    siliconflow_temperature: float = 0.7
    siliconflow_max_tokens: int = 500
    siliconflow_timeout_s: float = 30.0
    max_concurrent_requests: int = 10


def load_settings() -> Settings:
    paddle_ocr_token = _get_secret("PADDLE_OCR_TOKEN")

    base_url = _get_secret("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1"
    model = _get_secret("SILICONFLOW_MODEL") or "Pro/Qwen/Qwen2.5-7B-Instruct"
    vision_model = _get_secret("SILICONFLOW_VISION_MODEL") or "Qwen/Qwen3.5-27B"
    api_keys_raw = _get_secret("SILICONFLOW_API_KEYS") or ""
    api_keys = tuple(k.strip() for k in api_keys_raw.split(",") if k.strip())

    # Keep defaults unless explicitly overridden.
    temperature = float(_get_secret("SILICONFLOW_TEMPERATURE") or 0.7)
    max_tokens = int(_get_secret("SILICONFLOW_MAX_TOKENS") or 500)
    timeout_s = float(_get_secret("SILICONFLOW_TIMEOUT_S") or 30.0)
    max_conc = int(_get_secret("SILICONFLOW_MAX_CONCURRENT_REQUESTS") or 10)

    return Settings(
        paddle_ocr_token=paddle_ocr_token,
        siliconflow_base_url=base_url,
        siliconflow_model=model,
        siliconflow_vision_model=vision_model,
        siliconflow_api_keys=api_keys,
        siliconflow_temperature=temperature,
        siliconflow_max_tokens=max_tokens,
        siliconflow_timeout_s=timeout_s,
        max_concurrent_requests=max_conc,
    )
