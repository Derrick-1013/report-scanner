# -*- coding: utf-8 -*-
"""LLM 客户端：OpenAI 兼容接口。未配置时返回 None，由检查器降级处理。"""
from __future__ import annotations

import json
import os
from typing import Optional

import requests


class LLMClient:
    """极简 OpenAI 兼容客户端。"""

    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip()
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
        self.enabled = bool(self.api_key)

    def available(self) -> bool:
        return self.enabled

    def chat_json(self, system: str, user: str, timeout: int = 60) -> Optional[dict]:
        """调用 chat completions 并解析 JSON 输出。失败返回 None。"""
        if not self.enabled:
            return None
        try:
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as exc:  # noqa: BLE001 —— 任何异常都视为 LLM 不可用
            print(f"[llm] call failed: {exc}")
            return None
