from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

_client: AsyncIOMotorClient[Any] | None = None
_memory_debates: dict[str, dict[str, Any]] = {}


async def connect_mongo() -> None:
    global _client
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=1200)
    try:
        await _client.admin.command("ping")
    except Exception:
        _client = None


async def close_mongo() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def database() -> AsyncIOMotorDatabase[Any] | None:
    if _client is None:
        return None
    return _client[get_settings().mongodb_db]


async def save_debate(debate: dict[str, Any]) -> None:
    db = database()
    if db is None:
        _memory_debates[debate["id"]] = debate
        return
    await db.debates.update_one({"id": debate["id"]}, {"$set": debate}, upsert=True)


async def get_debate(debate_id: str) -> dict[str, Any] | None:
    db = database()
    if db is None:
        return _memory_debates.get(debate_id)
    return await db.debates.find_one({"id": debate_id}, {"_id": False})


async def list_debates() -> list[dict[str, Any]]:
    db = database()
    if db is None:
        return list(_memory_debates.values())
    cursor = db.debates.find({}, {"_id": False}).sort("updated_at", -1).limit(20)
    return [item async for item in cursor]


async def list_debates_in_progress() -> list[dict[str, Any]]:
    db = database()
    if db is None:
        return [d for d in _memory_debates.values() if d.get("phase") != "finished"]
    cursor = db.debates.find({"phase": {"$ne": "finished"}}, {"_id": False}).limit(40)
    return [item async for item in cursor]


def storage_mode() -> str:
    return "mongodb" if database() is not None else "memory"
