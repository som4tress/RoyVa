"""Thin async client for the OpenCode REST session API (same endpoints the Telegram bridge uses)."""
from __future__ import annotations

import asyncio
import base64
from typing import Any, Optional

import httpx


class OpenCodeError(Exception):
    pass


class OpenCodeClient:
    def __init__(self, url: str, password: str, directory: str, transport: Optional[httpx.AsyncBaseTransport] = None):
        token = base64.b64encode(f"opencode:{password}".encode()).decode()
        self.directory = directory
        self.http = httpx.AsyncClient(base_url=url.rstrip("/"), headers={"Authorization": f"Basic {token}"}, timeout=20, transport=transport)

    async def _req(self, method: str, path: str, json: Any = None) -> Any:
        # Only idempotent reads are retried (transport errors / 5xx); writes are never repeated automatically.
        attempts = 3 if method == "GET" else 1
        for n in range(attempts):
            try:
                r = await self.http.request(method, path, json=json)
            except httpx.TransportError as e:
                if n + 1 == attempts:
                    raise OpenCodeError(f"{method} {path} -> {type(e).__name__}") from e
                await asyncio.sleep(0.3 * (n + 1))
                continue
            if r.status_code >= 500 and n + 1 < attempts:
                await asyncio.sleep(0.3 * (n + 1))
                continue
            break
        if r.status_code >= 400:
            raise OpenCodeError(f"{method} {path} -> HTTP {r.status_code}")
        if r.status_code == 204 or not r.content:
            return None
        v = r.json()
        return v.get("data", v) if isinstance(v, dict) else v

    async def mcp_status(self) -> dict[str, str]:
        rows = await self._req("GET", "/api/mcp")
        return {x["name"]: x["status"]["status"] for x in rows}

    async def create_session(self, agent: str, permissions: list[dict]) -> str:
        v = await self._req("POST", "/api/session", {"location": {"directory": self.directory}, "agent": agent, "permissions": permissions})
        return v["id"]

    async def set_permissions(self, sid: str, permissions: list[dict]) -> None:
        await self._req("PATCH", f"/api/session/{sid}", {"permissions": permissions})

    async def prompt(self, sid: str, text: str, delivery: str = "queue") -> None:
        await self._req("POST", f"/api/session/{sid}/prompt", {"text": text, "delivery": delivery})

    async def messages(self, sid: str) -> list[dict]:
        return await self._req("GET", f"/api/session/{sid}/message")

    async def session(self, sid: str) -> dict:
        return await self._req("GET", f"/api/session/{sid}")

    async def interrupt(self, sid: str) -> None:
        await self._req("POST", f"/api/session/{sid}/interrupt", {})

    async def aclose(self) -> None:
        await self.http.aclose()
