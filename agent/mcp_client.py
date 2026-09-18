# -*- coding: utf-8 -*-
"""iFinD MCP 轻量客户端（streamable HTTP 协议）。

配置（.env）：
- IFIND_MCP_URL   例如 https://api-mcp.51ifind.com:8643/ds-mcp-servers/hexin-ifind-ds-mcp
- IFIND_MCP_AUTH  MCP 配置中的 Authorization 凭证

本客户端仅封装本项目所需的 search_notice（公告语义查询）能力。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

import requests


class IFindMCPClient:
    def __init__(self) -> None:
        self.url = os.getenv("IFIND_MCP_URL", "").strip()
        self.auth = os.getenv("IFIND_MCP_AUTH", "").strip()
        self.enabled = bool(self.url and self.auth)
        self._session = requests.Session() if self.enabled else None
        self._inited = False
        self._msg_id = 0

    def available(self) -> bool:
        return self.enabled

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _post(self, payload: dict, timeout: int = 60) -> List[dict]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.auth,
        }
        r = self._session.post(self.url, headers=headers, json=payload, timeout=timeout)
        ct = r.headers.get("content-type", "")
        if ct.startswith("text/event-stream"):
            out: List[dict] = []
            for line in r.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    d = line[5:].strip()
                    if d:
                        out.append(json.loads(d))
            return out
        try:
            return [r.json()]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"iFinD MCP 非 JSON 响应: {r.text[:200]}") from exc

    def _rpc(self, method: str, params: Optional[dict] = None) -> Optional[dict]:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            payload["params"] = params
        evs = self._post(payload)
        for ev in evs:
            if ev.get("id") == payload["id"]:
                if "error" in ev:
                    raise RuntimeError(f"iFinD MCP 错误: {json.dumps(ev['error'], ensure_ascii=False)[:300]}")
                return ev.get("result")
        return None

    def _ensure_init(self) -> None:
        if not self.enabled or self._inited:
            return
        self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "report-scanner", "version": "1.0.0"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._inited = True

    def search_notice(
        self,
        query: str,
        size: int = 3,
        time_start: Optional[str] = None,
        time_end: Optional[str] = None,
    ) -> Optional[List[str]]:
        """A股/基金/港美股公告内容语义查询，返回公告片段文本列表。失败返回 None。"""
        if not self.enabled:
            return None
        try:
            self._ensure_init()
            args: dict = {"query": query, "size": size}
            if time_start:
                args["time_start"] = time_start
            if time_end:
                args["time_end"] = time_end
            result = self._rpc("tools/call", {"name": "search_notice", "arguments": args})
            if not result or result.get("isError"):
                return None
            content = result.get("content") or []
            pieces: List[str] = []
            for c in content:
                if c.get("type") != "text":
                    continue
                txt = c.get("text") or ""
                try:
                    payload = json.loads(txt)
                    data = payload.get("data")
                    if isinstance(data, str):
                        data = json.loads(data)
                    if isinstance(data, list):
                        for it in data:
                            seg = (it.get("公告片段内容") or "").strip()
                            if seg:
                                pieces.append(seg)
                except Exception:  # noqa: BLE001
                    if txt.strip():
                        pieces.append(txt.strip())
            return pieces or None
        except Exception as exc:  # noqa: BLE001
            print(f"[ifind] search_notice failed: {exc}")
            return None
