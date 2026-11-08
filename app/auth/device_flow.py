# c:\Kortik\Kortik-Listener-App\app\auth\device_flow.py
"""
Orkestracija uparivanja uredjaja.

    start()  -> backend vrati {device_code, user_code, verification_uri}
    UI       -> korisnik otvori verification_uri i potvrdi 6-cifreni kod
    wait()   -> app polira /auth/device/token dok ne dobije tokene

Tajne (device_secret, refresh_token) idu iskljucivo u SecretStore (DPAPI).
Access token zivi samo u memoriji.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app.net.api import ApiError, ListenerApi, PendingApproval
from app.security.storage import SecretStore


@dataclass
class PairingSession:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    started_at: float

    @property
    def expires_at(self) -> float:
        return self.started_at + self.expires_in

    def seconds_left(self) -> int:
        return max(0, int(self.expires_at - time.time()))


class DeviceFlow:
    def __init__(self, api: ListenerApi, store: SecretStore):
        self.api = api
        self.store = store
        self.session: Optional[PairingSession] = None

    async def start(self, device_name: str, app_version: str) -> PairingSession:
        data = await self.api.device_start(name=device_name, app_version=app_version)
        self.session = PairingSession(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data.get("verification_uri", ""),
            expires_in=int(data.get("expires_in") or 600),
            interval=max(2, int(data.get("interval") or 3)),
            started_at=time.time(),
        )
        return self.session

    async def wait_for_token(
        self,
        on_tick: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Polira token endpoint dok korisnik ne potvrdi kod ili ne istekne vreme."""
        if not self.session:
            raise ApiError(0, "no_pairing_session", "Uparivanje nije započeto.")

        deadline = self.session.expires_at
        while time.time() < deadline:
            if on_tick:
                on_tick(self.session.seconds_left())
            try:
                data = await self.api.device_token(self.session.device_code)
                self._persist(data)
                return data
            except PendingApproval:
                await asyncio.sleep(self.session.interval)
            except ApiError as e:
                # 404/409/410 -> kod je nevazeci/iskoriscen; nema smisla cekati
                if e.status in (404, 409, 410):
                    raise
                await asyncio.sleep(self.session.interval)

        raise ApiError(410, "pairing_timeout", "Kod je istekao. Pokreni uparivanje ponovo.")

    def _persist(self, data: Dict[str, Any]) -> None:
        self.store.save(
            {
                "device_id": data.get("device_id"),
                "device_secret": data.get("device_secret"),
                "refresh_token": data.get("refresh_token"),
                "user_id": data.get("user_id"),
                "saved_at": int(time.time()),
            }
        )

    async def refresh(self, device_id: str, refresh_token: str) -> Dict[str, Any]:
        data = await self.api.device_refresh(device_id, refresh_token)
        current = self.store.load() or {}
        current.update(
            {
                "device_id": data.get("device_id") or device_id,
                "refresh_token": data.get("refresh_token"),
                "user_id": data.get("user_id") or current.get("user_id"),
                "refreshed_at": int(time.time()),
            }
        )
        # device_secret se NE menja pri refresh-u
        self.store.save(current)
        return data

    def unlink(self) -> None:
        self.store.clear()
        self.session = None
