# c:\Kortik\Kortik-Listener-App\app\net\api.py
"""
Async klijent za Kortik backend.

Sve rute su pod /api/listener. Komanda se potpisuje HMAC-om nad TACNO onim
bajtovima koji se salju (`raw_body`), pa backend moze da je verifikuje.
"""
from __future__ import annotations

import json
import ssl
import uuid
from typing import Any, Dict, Optional

import aiohttp

from app.security.request_signer import signed_headers
from app.version import APP_VERSION, PLATFORM, USER_AGENT

COMMAND_PATH = "/api/listener/command"
TRANSCRIBE_PATH = "/api/listener/transcribe"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", payload: Optional[Dict[str, Any]] = None):
        self.status = status
        self.code = code
        self.message = message or code
        self.payload = payload or {}
        super().__init__(f"[{status}] {self.code}: {self.message}")

    @property
    def retry_after(self) -> int:
        try:
            return int(self.payload.get("retry_after") or 0)
        except (TypeError, ValueError):
            return 0


class PendingApproval(ApiError):
    """Korisnik jos nije potvrdio kod na dashboardu (HTTP 428)."""


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:
        pass
    return context


def _error_code(status: int, data: Dict[str, Any]) -> str:
    return str(data.get("status") or data.get("detail") or data.get("message") or f"http_{status}")


class ListenerApi:
    def __init__(self, base_url: str, session: Optional[aiohttp.ClientSession] = None):
        self.base_url = str(base_url).rstrip("/")
        self._session = session
        self._own_session = session is None

    async def __aenter__(self) -> "ListenerApi":
        await self.start()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is not None:
            return
        connector = aiohttp.TCPConnector(limit=8, ttl_dns_cache=300, ssl=_ssl_context())
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=15, connect=5),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def close(self) -> None:
        if self._own_session and self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple:
        if self._session is None:
            await self.start()
        assert self._session is not None

        url = f"{self.base_url}{path}"
        kwargs: Dict[str, Any] = {"headers": dict(headers or {})}
        if raw_body is not None:
            kwargs["data"] = raw_body
            kwargs["headers"].setdefault("Content-Type", "application/json")
        elif json_body is not None:
            kwargs["json"] = json_body

        try:
            async with self._session.request(method, url, **kwargs) as response:
                text = await response.text()
                status = response.status
        except aiohttp.ClientError as e:
            raise ApiError(0, "network_error", f"Ne mogu da se povežem na server: {e}") from e

        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            data = {"raw": text[:300]}

        return status, (data if isinstance(data, dict) else {"data": data})

    # ── Device flow ─────────────────────────────────────────────────────────
    async def device_start(
        self,
        name: str,
        platform: str = PLATFORM,
        app_version: str = APP_VERSION,
    ) -> Dict[str, Any]:
        status, data = await self._request(
            "POST",
            "/api/listener/auth/device/start",
            json_body={"name": name, "platform": platform, "app_version": app_version},
        )
        if status != 200:
            raise ApiError(status, _error_code(status, data), data.get("detail", ""), data)
        return data

    async def device_token(self, device_code: str) -> Dict[str, Any]:
        status, data = await self._request(
            "POST",
            "/api/listener/auth/device/token",
            json_body={"device_code": device_code},
        )
        if status == 428:
            raise PendingApproval(428, "pending_approval", "Kod još nije potvrđen na dashboardu.")
        if status != 200:
            raise ApiError(status, _error_code(status, data), data.get("detail", ""), data)
        return data

    async def device_refresh(self, device_id: str, refresh_token: str) -> Dict[str, Any]:
        status, data = await self._request(
            "POST",
            "/api/listener/auth/device/refresh",
            json_body={"device_id": device_id, "refresh_token": refresh_token},
        )
        if status != 200:
            raise ApiError(status, _error_code(status, data), data.get("detail", ""), data)
        return data

    # ── Radne rute ──────────────────────────────────────────────────────────
    async def heartbeat(
        self,
        access_token: str,
        app_version: str = APP_VERSION,
        listening: bool = True,
        device_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        status, data = await self._request(
            "POST",
            "/api/listener/heartbeat",
            json_body={
                "app_version": app_version,
                "listening": bool(listening),
                "device_name": device_name,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if status != 200:
            raise ApiError(status, _error_code(status, data), data.get("detail", ""), data)
        return data

    async def send_command(
        self,
        access_token: str,
        device_secret: str,
        command: str,
        query: str = "",
        request_id: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "command": command,
            "query": query or "",
            "request_id": request_id or str(uuid.uuid4()),
        }
        if guild_id:
            payload["guild_id"] = int(guild_id)

        raw = json.dumps(
            payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        headers.update(signed_headers(device_secret, "POST", COMMAND_PATH, raw))

        status, data = await self._request("POST", COMMAND_PATH, raw_body=raw, headers=headers)
        result = dict(data)
        result["http_status"] = status
        return result

    async def transcribe_audio(
        self,
        access_token: str,
        device_secret: str,
        wav_bytes: bytes,
        language: str = "sr",
    ) -> Dict[str, Any]:
        """Cloud STT: salje kratak WAV (16 kHz mono) na backend, HMAC-potpisan."""
        import base64

        payload = {
            "audio_b64": base64.b64encode(wav_bytes).decode("ascii"),
            "language": (language or "sr")[:8],
            "duration_ms": 0,
        }
        raw = json.dumps(
            payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        headers.update(signed_headers(device_secret, "POST", TRANSCRIBE_PATH, raw))

        status, data = await self._request("POST", TRANSCRIBE_PATH, raw_body=raw, headers=headers)
        result = dict(data)
        result["http_status"] = status
        return result

    async def check_update(
        self, channel: str = "stable", platform: str = PLATFORM
    ) -> Optional[Dict[str, Any]]:
        status, data = await self._request(
            "GET", f"/api/listener/version?channel={channel}&platform={platform}"
        )
        if status == 404:
            return None
        if status != 200:
            raise ApiError(status, _error_code(status, data), data.get("detail", ""), data)
        return data
