from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass

import requests

from .config import Settings


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class SiliconFlowClient:
    """
    Minimal OpenAI-compatible chat.completions client for SiliconFlow.
    - Rotates API keys for burst concurrency
    - Retries on transient HTTP errors / 429
    """

    def __init__(self, settings: Settings):
        if not settings.siliconflow_api_keys:
            raise RuntimeError(
                "Missing SILICONFLOW_API_KEYS (comma-separated in .streamlit/secrets.toml or env var)."
            )
        self._settings = settings
        self._keys = list(settings.siliconflow_api_keys)
        self._lock = threading.Lock()
        self._rr = 0

    def _next_key(self) -> str:
        with self._lock:
            k = self._keys[self._rr % len(self._keys)]
            self._rr += 1
            return k

    def chat_completions(
        self,
        *,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_s: float | None = None,
        max_retries: int = 3,
    ) -> str:
        url = self._settings.siliconflow_base_url.rstrip("/") + "/chat/completions"
        model = model or self._settings.siliconflow_model
        temperature = temperature if temperature is not None else self._settings.siliconflow_temperature
        max_tokens = max_tokens if max_tokens is not None else self._settings.siliconflow_max_tokens
        timeout_s = timeout_s if timeout_s is not None else self._settings.siliconflow_timeout_s

        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [m.__dict__ for m in messages],
        }

        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            api_key = self._next_key()
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                if resp.status_code in (429, 500, 502, 503, 504):
                    # Exponential backoff with jitter.
                    sleep_s = (2**attempt) * 0.5 + random.random() * 0.2
                    time.sleep(min(sleep_s, 5.0))
                    continue
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"Empty choices in response: {json.dumps(data, ensure_ascii=False)[:500]}")
                msg = (choices[0].get("message") or {}).get("content")
                if not msg:
                    raise RuntimeError(f"Empty message content: {json.dumps(data, ensure_ascii=False)[:500]}")
                return str(msg)
            except Exception as e:  # noqa: BLE001
                last_err = e
                sleep_s = (2**attempt) * 0.3 + random.random() * 0.2
                time.sleep(min(sleep_s, 3.0))
                continue

        raise RuntimeError(f"SiliconFlow request failed after retries: {last_err}")

    def vision_understand(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/png",
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int = 2,
    ) -> str:
        """
        Multimodal call using OpenAI-style content parts.
        Note: requires the upstream API/model to support image inputs.
        """
        url = self._settings.siliconflow_base_url.rstrip("/") + "/chat/completions"
        model = model or self._settings.siliconflow_vision_model
        timeout_s = timeout_s if timeout_s is not None else self._settings.siliconflow_timeout_s

        import base64

        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }

        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            api_key = self._next_key()
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                if resp.status_code in (429, 500, 502, 503, 504):
                    sleep_s = (2**attempt) * 0.5 + random.random() * 0.2
                    time.sleep(min(sleep_s, 5.0))
                    continue
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                msg = (choices[0].get("message") or {}).get("content") if choices else None
                if not msg:
                    raise RuntimeError(f"Empty vision message content: {json.dumps(data, ensure_ascii=False)[:500]}")
                return str(msg)
            except Exception as e:  # noqa: BLE001
                last_err = e
                sleep_s = (2**attempt) * 0.3 + random.random() * 0.2
                time.sleep(min(sleep_s, 3.0))
                continue
        raise RuntimeError(f"SiliconFlow vision request failed after retries: {last_err}")
