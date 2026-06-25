"""轻量向量检索：哈希嵌入 + SQLite，无需 Ollama / 本地大模型。"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

from app.models import Source

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DB_PATH = _PROJECT_ROOT / "data" / "vector_index.sqlite"
_EMBED_DIM = 384
_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower())


def embed_text(text: str, dim: int = _EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        for seed in (token, token[:2], token[-2:] if len(token) > 2 else token):
            idx = hash(seed) % dim
            sign = 1.0 if (hash(seed + ":s") % 2) == 0 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONN = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _CONN.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                debate_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                excerpt TEXT NOT NULL,
                url TEXT,
                reliability REAL,
                embedding TEXT NOT NULL
            )
            """
        )
        _CONN.commit()
        _migrate_schema(_CONN)
    return _CONN


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if "debate_id" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN debate_id TEXT NOT NULL DEFAULT ''")
        conn.commit()


def upsert_sources(sources: list[Source], *, debate_id: str = "") -> None:
    with _LOCK:
        conn = _get_conn()
        for source in sources:
            text = f"{source.title} {source.excerpt}"
            conn.execute(
                """
                INSERT INTO chunks (id, debate_id, title, excerpt, url, reliability, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    debate_id=excluded.debate_id,
                    title=excluded.title,
                    excerpt=excluded.excerpt,
                    url=excluded.url,
                    reliability=excluded.reliability,
                    embedding=excluded.embedding
                """,
                (
                    source.id,
                    debate_id,
                    source.title,
                    source.excerpt,
                    source.url,
                    source.reliability,
                    json.dumps(embed_text(text)),
                ),
            )
        conn.commit()


def delete_debate_materials(debate_id: str) -> int:
    with _LOCK:
        conn = _get_conn()
        cur = conn.execute("DELETE FROM chunks WHERE debate_id = ?", (debate_id,))
        conn.commit()
        return cur.rowcount


def search(
    query: str,
    top_k: int = 4,
    *,
    debate_id: str | None = None,
) -> list[tuple[Source, float]]:
    qvec = embed_text(query)
    with _LOCK:
        conn = _get_conn()
        if debate_id:
            rows = conn.execute(
                "SELECT id, title, excerpt, url, reliability, embedding, debate_id FROM chunks WHERE debate_id = ?",
                (debate_id,),
            ).fetchall()
            global_rows = conn.execute(
                "SELECT id, title, excerpt, url, reliability, embedding, debate_id FROM chunks WHERE debate_id = ''",
            ).fetchall()
            rows = list(rows) + list(global_rows)
        else:
            rows = conn.execute(
                "SELECT id, title, excerpt, url, reliability, embedding, debate_id FROM chunks"
            ).fetchall()

    ranked: list[tuple[Source, float]] = []
    for row in rows:
        vec = json.loads(row[5])
        score = _cosine(qvec, vec)
        if row[6] == debate_id and debate_id:
            score += 0.12
        ranked.append(
            (
                Source(
                    id=row[0],
                    title=row[1],
                    excerpt=row[2],
                    url=row[3],
                    reliability=row[4] or 0.8,
                ),
                score,
            )
        )
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def bootstrap_if_empty(seed_sources: list[Source]) -> None:
    with _LOCK:
        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) FROM chunks WHERE debate_id = ''").fetchone()[0]
    if count == 0:
        upsert_sources(seed_sources, debate_id="")


def chunk_plaintext(text: str, *, max_chars: int = 480) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        if len(part) <= max_chars:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.append(part)
            continue
        sentences = re.split(r"(?<=[。！？.!?])\s*", part)
        for sentence in sentences:
            if not sentence:
                continue
            if len(buffer) + len(sentence) > max_chars and buffer:
                chunks.append(buffer)
                buffer = sentence
            else:
                buffer = f"{buffer}{sentence}" if buffer else sentence
        if buffer:
            chunks.append(buffer)
            buffer = ""
    return chunks or [text[:max_chars]]


def ingest_uploaded_text(
    *,
    debate_id: str,
    title: str,
    content: str,
    reliability: float = 0.88,
) -> list[Source]:
    pieces = chunk_plaintext(content)
    sources: list[Source] = []
    for index, piece in enumerate(pieces, start=1):
        sources.append(
            Source(
                id=f"mat-{debate_id[:8]}-{uuid4().hex[:8]}",
                title=f"{title} · 片段 {index}",
                excerpt=piece,
                reliability=reliability,
            )
        )
    upsert_sources(sources, debate_id=debate_id)
    return sources
