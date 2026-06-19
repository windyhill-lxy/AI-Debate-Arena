"""联机席位在线状态：WS 短断延迟离线，重连恢复 connected。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

OFFLINE_GRACE_SECONDS = 4.0
_pending_offline: dict[tuple[str, str], asyncio.Task[Any]] = {}


def cancel_pending_offline(debate_id: str, participant_id: str) -> None:
    key = (debate_id, participant_id)
    task = _pending_offline.pop(key, None)
    if task and not task.done():
        task.cancel()


def schedule_participant_offline(
    debate_id: str,
    participant_id: str,
    *,
    is_still_connected: Callable[[], bool],
    mark_offline: Callable[[], Awaitable[None]],
) -> None:
    cancel_pending_offline(debate_id, participant_id)

    async def _run() -> None:
        try:
            await asyncio.sleep(OFFLINE_GRACE_SECONDS)
            if is_still_connected():
                logger.debug(
                    "presence skip offline debate=%s participant=%s (reconnected)",
                    debate_id,
                    participant_id,
                )
                return
            await mark_offline()
            logger.info("presence offline debate=%s participant=%s", debate_id, participant_id)
        except asyncio.CancelledError:
            raise
        finally:
            _pending_offline.pop((debate_id, participant_id), None)

    _pending_offline[(debate_id, participant_id)] = asyncio.create_task(_run())


def reset_presence_tasks() -> None:
    """测试用：清空待执行的离线任务。"""
    for task in list(_pending_offline.values()):
        if not task.done():
            task.cancel()
    _pending_offline.clear()
