import logging
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, list[dict]] = {}

    async def connect(
        self,
        debate_id: str,
        websocket: WebSocket,
        *,
        viewer_side: str | None = None,
        participant_id: str | None = None,
        viewer_mode: str | None = None,
    ) -> dict:
        await websocket.accept()
        entry = {
            "socket": websocket,
            "connection_id": uuid4().hex[:12],
            "viewer_side": viewer_side,
            "participant_id": participant_id,
            "viewer_mode": viewer_mode,
        }
        self.active.setdefault(debate_id, []).append(entry)
        logger.debug(
            "ws connect debate=%s connection=%s participant=%s",
            debate_id,
            entry["connection_id"],
            participant_id,
        )
        return entry

    def touch(self, debate_id: str, websocket: WebSocket) -> None:
        for entry in self.active.get(debate_id, []):
            if entry.get("socket") is websocket:
                entry["last_seen"] = True
                return

    def update_connection_meta(
        self,
        debate_id: str,
        websocket: WebSocket,
        *,
        viewer_side: str | None = None,
        viewer_mode: str | None = None,
    ) -> bool:
        for entry in self.active.get(debate_id, []):
            if entry.get("socket") is websocket:
                if viewer_side in {"affirmative", "negative", "spectator", None}:
                    if viewer_side is not None:
                        entry["viewer_side"] = viewer_side
                if viewer_mode is not None:
                    entry["viewer_mode"] = viewer_mode
                return True
        return False

    def disconnect(self, debate_id: str, websocket: WebSocket) -> dict | None:
        connections = self.active.get(debate_id, [])
        removed: dict | None = None
        kept: list[dict] = []
        for entry in connections:
            if entry.get("socket") is websocket:
                removed = entry
            else:
                kept.append(entry)
        if kept:
            self.active[debate_id] = kept
        elif debate_id in self.active:
            del self.active[debate_id]
        if removed:
            logger.debug(
                "ws disconnect debate=%s connection=%s participant=%s",
                debate_id,
                removed.get("connection_id"),
                removed.get("participant_id"),
            )
        return removed

    def participant_connection_count(self, debate_id: str, participant_id: str | None) -> int:
        if not participant_id:
            return 0
        return sum(
            1
            for entry in self.active.get(debate_id, [])
            if entry.get("participant_id") == participant_id
        )

    async def disconnect_participant(self, debate_id: str, participant_id: str) -> int:
        closed = 0
        for entry in list(self.active.get(debate_id, [])):
            if entry.get("participant_id") != participant_id:
                continue
            socket = entry["socket"]
            try:
                await socket.close()
                closed += 1
            except Exception:
                logger.warning(
                    "failed to close socket debate=%s participant=%s",
                    debate_id,
                    participant_id,
                    exc_info=True,
                )
            self.disconnect(debate_id, socket)
        return closed

    async def relay_signal(self, debate_id: str, sender: WebSocket, payload: dict) -> None:
        sender_entry = next(
            (entry for entry in self.active.get(debate_id, []) if entry.get("socket") is sender),
            None,
        )
        if sender_entry is None:
            return
        claimed_id = payload.get("from_participant_id")
        actual_id = sender_entry.get("participant_id")
        if not claimed_id or not actual_id or claimed_id != actual_id:
            return
        target_id = payload.get("to_participant_id")
        for entry in list(self.active.get(debate_id, [])):
            socket = entry["socket"]
            if socket is sender:
                continue
            if target_id and entry.get("participant_id") != target_id:
                continue
            try:
                await socket.send_json(payload)
            except Exception:
                logger.warning(
                    "relay_signal send failed debate=%s connection=%s",
                    debate_id,
                    entry.get("connection_id"),
                    exc_info=True,
                )
                self.disconnect(debate_id, socket)

    async def broadcast(self, debate_id: str, payload: dict) -> None:
        for entry in list(self.active.get(debate_id, [])):
            socket = entry["socket"]
            try:
                await socket.send_json(payload)
            except Exception:
                logger.warning(
                    "broadcast send failed debate=%s connection=%s",
                    debate_id,
                    entry.get("connection_id"),
                    exc_info=True,
                )
                self.disconnect(debate_id, socket)

    async def broadcast_filtered(self, debate_id: str, payload: dict, predicate) -> None:
        for entry in list(self.active.get(debate_id, [])):
            socket = entry["socket"]
            try:
                if predicate(payload, entry):
                    await socket.send_json(payload)
            except Exception:
                logger.warning(
                    "broadcast_filtered send failed debate=%s connection=%s",
                    debate_id,
                    entry.get("connection_id"),
                    exc_info=True,
                )
                self.disconnect(debate_id, socket)

    async def broadcast_state(self, debate_id: str, event: str, debate, serializer) -> None:
        for entry in list(self.active.get(debate_id, [])):
            socket = entry["socket"]
            try:
                await socket.send_json(
                    {
                        "event": event,
                        "debate": serializer(
                            debate,
                            viewer_side=entry.get("viewer_side"),
                            participant_id=entry.get("participant_id"),
                            viewer_mode=entry.get("viewer_mode"),
                        ),
                    }
                )
            except Exception:
                logger.warning(
                    "broadcast_state send failed debate=%s event=%s connection=%s",
                    debate_id,
                    event,
                    entry.get("connection_id"),
                    exc_info=True,
                )
                self.disconnect(debate_id, socket)


manager = ConnectionManager()
