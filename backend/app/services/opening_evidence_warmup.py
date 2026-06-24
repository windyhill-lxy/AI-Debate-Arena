from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.time_utils import utc_now
from app.db.mongo import get_debate
from app.models import DebateState
from app.services.argument_bank import add_argument_items
from app.services.opening_evidence import ensure_opening_argument_bank, opening_evidence_completed

logger = logging.getLogger(__name__)

PersistAndBroadcast = Callable[[DebateState, str], Awaitable[DebateState]]
OnReady = Callable[[str], None]

_warmup_tasks: dict[str, asyncio.Task] = {}


@dataclass(frozen=True)
class OpeningEvidenceWarmupResult:
    ready: bool


def opening_evidence_warmup_running(debate_id: str) -> bool:
    task = _warmup_tasks.get(debate_id)
    return task is not None and not task.done()


def cancel_opening_evidence_warmup(debate_id: str) -> None:
    task = _warmup_tasks.pop(debate_id, None)
    if task is not None and not task.done():
        task.cancel()


async def run_opening_evidence_warmup_once(
    debate_id: str,
    topic_snapshot: str,
    *,
    persist_and_broadcast: PersistAndBroadcast | None = None,
    on_ready: OnReady | None = None,
) -> OpeningEvidenceWarmupResult:
    doc = await get_debate(debate_id)
    if doc is None:
        return OpeningEvidenceWarmupResult(ready=False)
    warmup_state = DebateState.model_validate(doc)
    if warmup_state.phase == "finished" or warmup_state.topic != topic_snapshot:
        return OpeningEvidenceWarmupResult(ready=False)

    await ensure_opening_argument_bank(warmup_state, force=True)

    latest_doc = await get_debate(debate_id)
    if latest_doc is None:
        return OpeningEvidenceWarmupResult(ready=False)
    latest = DebateState.model_validate(latest_doc)
    if latest.phase == "finished" or latest.topic != topic_snapshot:
        return OpeningEvidenceWarmupResult(ready=False)
    if opening_evidence_completed(latest):
        if on_ready is not None:
            on_ready(latest.id)
        return OpeningEvidenceWarmupResult(ready=True)

    for side in ("affirmative", "negative"):
        add_argument_items(latest, side, warmup_state.argument_bank.get(side, []))
    latest.argument_bank_locked = latest.argument_bank_locked or warmup_state.argument_bank_locked
    latest.opening_evidence_completed = latest.opening_evidence_completed or warmup_state.opening_evidence_completed
    latest.updated_at = utc_now()

    if persist_and_broadcast is not None:
        await persist_and_broadcast(latest, "opening_argument_bank_warmed")
    else:
        from app.db.mongo import save_debate

        await save_debate(latest.model_dump(mode="json"))
    ready = opening_evidence_completed(latest)
    if ready and on_ready is not None:
        on_ready(latest.id)
    return OpeningEvidenceWarmupResult(ready=ready)


def start_opening_evidence_warmup(
    debate_id: str,
    topic_snapshot: str,
    *,
    persist_and_broadcast: PersistAndBroadcast,
    on_ready: OnReady | None = None,
) -> None:
    if opening_evidence_warmup_running(debate_id):
        return

    async def run() -> None:
        try:
            await run_opening_evidence_warmup_once(
                debate_id,
                topic_snapshot,
                persist_and_broadcast=persist_and_broadcast,
                on_ready=on_ready,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("opening evidence warmup failed for debate %s", debate_id)
        finally:
            current = _warmup_tasks.get(debate_id)
            if current is asyncio.current_task():
                _warmup_tasks.pop(debate_id, None)

    _warmup_tasks[debate_id] = asyncio.create_task(run())
