"""AMC eval-plane storage: `add_requests` + `memories`, atomic multi-message ingest.

Self-contained on purpose: never imports the business `config` / `models` /
`routers` modules, so this can run as its own process/container (standalone
evaluation app) without pulling in the full Minta API app or its side effects
(auto-scanner, auth RuntimeError, .env writes, ...).

Contract shape (Agent Memory Leaderboard Add contract):
  * one Add request carries an ordered `messages[]` list (a whole conversation
    is normally one request; the platform splits at >20 messages / >2000 words)
  * every message must be durable and searchable before the endpoint returns 200
  * exact re-delivery of a `request_id` (platform retries / resume) must be
    idempotent: same ids, same data, same success response
  * storage must be lossless: repeated content is still stored (retrieval-side
    suppression is a separate concern, handled by the retriever)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

Base = declarative_base()

DEFAULT_DB = "sqlite:///./eval.db"


def mem_id(request_id: str, msg_index: int) -> str:
    """Deterministic memory id, stable across exact platform retries."""
    digest = hashlib.sha256(f"{request_id}:{msg_index}".encode("utf-8")).hexdigest()
    return f"mem_{digest[:16]}"


class AddRequest(Base):
    __tablename__ = "add_requests"

    request_id = Column(String(256), primary_key=True)
    user_id = Column(String(256), nullable=False, index=True)
    session_id = Column(String(256), nullable=False)
    payload_hash = Column(String(64), nullable=False)  # audit only; retries trusted by request_id
    completed_at = Column(DateTime, server_default=func.now(), nullable=False)


class Memory(Base):
    __tablename__ = "memories"

    id = Column(String(64), primary_key=True)
    request_id = Column(String(256), nullable=False, index=True)
    msg_index = Column(Integer, nullable=False)
    user_id = Column(String(256), nullable=False, index=True)
    session_id = Column(String(256), nullable=False)
    role = Column(String(16), nullable=True)
    raw_content = Column(Text, nullable=False)
    timestamp_ms = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    embedding = Column(LargeBinary, nullable=True)  # float32 bytes (numpy), optional per arm
    signals = Column(Text, nullable=True)           # JSON string, experiment arms only

    __table_args__ = (
        UniqueConstraint("request_id", "msg_index", name="uq_request_msg_index"),
    )


class EvalStore:
    """SQLite-backed store for one evaluation run.

    `user_id` is the only isolation namespace (contract requirement); every
    query path filters on it first.
    """

    def __init__(self, db_url: str | None = None):
        url = (db_url or os.environ.get("MINTA_EVAL_DB") or DEFAULT_DB).rstrip("/")
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self._url = url
        self._engine = create_engine(url, **kwargs)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Base.metadata.create_all(self._engine)
        if self._url.startswith("sqlite"):
            with self._engine.begin() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")

    # ── write path ─────────────────────────────────────────────────────────

    def add_batch(self, request_id: str, user_id: str, session_id: str,
                  messages: list[dict], embed_fn=None,
                  embed_batch_fn=None) -> tuple[str, int]:
        """Atomically ingest one Add request. Returns (status, n_memories).

        status is "created" for a fresh request_id or "duplicate" when the same
        request_id already completed (caller echoes 200 in both cases).
        `embed_fn(content) -> bytes` runs for EVERY message BEFORE any row is
        written, so a mid-batch embedding failure leaves zero rows and the
        platform retry starts clean. `embed_batch_fn(contents) -> list[bytes]`
        is preferred when available (batch encode is far faster under the
        platform's Add concurrency).
        """
        payload_hash = hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        with self._lock:
            with self._Session() as db:
                if db.get(AddRequest, request_id) is not None:
                    return "duplicate", 0

                embeds: list = []
                if embed_fn is not None or embed_batch_fn is not None:
                    if embed_batch_fn is not None and len(messages) > 1:
                        embeds = embed_batch_fn(
                            [m.get("content", "") for m in messages])
                    else:
                        embeds = [embed_fn(m.get("content", "")) for m in messages]

                db.add(AddRequest(
                    request_id=request_id,
                    user_id=user_id,
                    session_id=session_id,
                    payload_hash=payload_hash,
                ))
                db.add_all([
                    Memory(
                        id=mem_id(request_id, i),
                        request_id=request_id,
                        msg_index=i,
                        user_id=user_id,
                        session_id=session_id,
                        role=m.get("role"),
                        raw_content=m.get("content", ""),
                        timestamp_ms=m.get("timestamp"),
                        embedding=embeds[i] if embeds else None,
                    )
                    for i, m in enumerate(messages)
                ])
                db.commit()
        return "created", len(messages)

    def session(self):
        """Raw session for operational/testing access (caller closes)."""
        return self._Session()

    # ── read path (used by the retriever) ──────────────────────────────────

    def memories_for_user(self, user_id: str) -> list[dict]:
        """All memories of one user, in (request_id, msg_index) order.

        (request_id, msg_index) is the adjacency key the retriever needs for
        the neighbour-window expansion.
        """
        with self._Session() as db:
            rows = (
                db.query(Memory)
                .filter(Memory.user_id == user_id)
                .order_by(Memory.request_id, Memory.msg_index)
                .all()
            )
            return [self._row_to_dict(r) for r in rows]

    def count_memories(self, user_id: str | None = None) -> int:
        with self._Session() as db:
            q = db.query(Memory)
            if user_id is not None:
                q = q.filter(Memory.user_id == user_id)
            return q.count()

    # ── data hygiene ───────────────────────────────────────────────────────

    def ttl_cleanup(self, hours: int) -> int:
        """Delete requests/memories older than `hours` (0 disables).

        Meets the ≤30-day retention obligation for self-hosted fallback;
        platform-deployed containers are destroyed after the run anyway.
        """
        if hours <= 0:
            return 0
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
        deleted = 0
        with self._lock:
            with self._Session() as db:
                stale = db.query(AddRequest.request_id).filter(
                    AddRequest.completed_at < cutoff).all()
                ids = [r[0] for r in stale]
                if ids:
                    deleted += db.query(Memory).filter(
                        Memory.request_id.in_(ids)).delete(synchronize_session=False)
                    deleted += db.query(AddRequest).filter(
                        AddRequest.request_id.in_(ids)).delete(synchronize_session=False)
                    db.commit()
        return deleted

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row.id,
            "request_id": row.request_id,
            "msg_index": row.msg_index,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "role": row.role,
            "raw_content": row.raw_content,
            "timestamp_ms": row.timestamp_ms,
            "created_at": row.created_at,
            "embedding": row.embedding,
        }
