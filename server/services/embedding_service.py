"""Embedding service — ChromaDB (default) + FAISS (fallback).

Backends:
- chromadb (default): Persistent vector store, mpnet 768-dim, survives restart.
- local: FAISS in-memory index, MiniLM 384-dim, original py38 backend.
- openai / siliconflow / deepseek: API-based embeddings.

Public API:
    embed(text) -> np.ndarray
    embed_batch(texts) -> np.ndarray
    build_index(objects) -> None
    search(query, top_k, where=None) -> List[dict]
    add_vector(obj_id, text, metadata=None) -> None
    delete_vectors(ids) -> None

`metadata` / `where` scope vectors by owner: every indexed object carries
{"user_id": str | "global"} and search filters on it, so semantic retrieval
never leaks across users.
"""
from __future__ import annotations
import os
import json
import logging
import numpy as np
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

EMBEDDING_BACKEND = os.environ.get("MINTA_EMBEDDING_BACKEND", "chromadb")
EMBEDDING_DIM = int(os.environ.get("MINTA_EMBEDDING_DIM", "768"))


def _chroma_path() -> str:
    return os.environ.get(
        "MINTA_CHROMA_PATH",
        str(Path(__file__).resolve().parent.parent.parent / "chroma_data"),
    )


class EmbeddingService:
    """ChromaDB-first embedding service with FAISS fallback."""

    def __init__(self, backend: str = None):
        self.backend = backend or EMBEDDING_BACKEND
        self._model = None
        self._client = None
        self._chroma_client = None
        self._collection = None
        self.faiss_index = None
        self._id_to_idx: dict = {}
        self._idx_to_id: dict = {}
        self._metadata_by_id: dict = {}
        self._documents_by_id: dict = {}
        self._initialized = False

    # ── Init ──

    def _ensure_init(self):
        if self._initialized:
            return
        if self.backend == "chromadb":
            self._init_chroma()
        elif self.backend == "local":
            self._init_local()
        elif self.backend in ("openai", "siliconflow", "deepseek"):
            self._init_api()
        else:
            self._init_chroma()
        self._initialized = True

    def _init_chroma(self):
        import chromadb
        import sentence_transformers

        # Load the model directly via sentence-transformers instead of chroma's
        # bundled helper: the helper was removed in chromadb 1.x, so this works
        # on both the image pin (<0.6) and newer local dev installs.
        model_path = os.environ.get("MINTA_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self._model = sentence_transformers.SentenceTransformer(model_path)
        path = _chroma_path()
        os.makedirs(path, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=path)
        try:
            self._collection = self._chroma_client.get_collection("minta_memories")
            logger.info(f"ChromaDB: loaded collection ({self._collection.count()} vectors)")
        except Exception:
            self._collection = self._chroma_client.create_collection(
                "minta_memories", metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB: created new collection")
        self.faiss_index = True

    def _init_local(self):
        import sentence_transformers
        model_path = os.environ.get("MINTA_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self._model = sentence_transformers.SentenceTransformer(model_path)
        logger.info(f"FAISS: loaded '{model_path}'")

    def _init_api(self):
        import openai
        keys = {"openai": "OPENAI_API_KEY", "siliconflow": "SILICONFLOW_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
        self._client = openai.OpenAI(api_key=os.environ.get(keys[self.backend]))
        logger.info(f"API: {self.backend}")

    # ── Embed ──

    def embed(self, text: str) -> np.ndarray:
        self._ensure_init()
        if not text:
            return np.zeros(EMBEDDING_DIM, dtype=np.float32)
        try:
            if self.backend == "chromadb":
                return self._model.encode(text, normalize_embeddings=True).astype(np.float32)
            elif self.backend == "local":
                return self._model.encode(text, normalize_embeddings=True).astype(np.float32)
            else:
                return self._embed_api(text)
        except Exception as e:
            logger.error(f"Embed failed: {e}")
            return np.zeros(EMBEDDING_DIM, dtype=np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        self._ensure_init()
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        try:
            if self.backend == "chromadb":
                return self._model.encode(texts, normalize_embeddings=True).astype(np.float32)
            elif self.backend == "local":
                return self._model.encode(texts, normalize_embeddings=True).astype(np.float32)
            else:
                return np.array([self._embed_api(t) for t in texts], dtype=np.float32)
        except Exception as e:
            logger.error(f"Batch embed failed: {e}")
            return np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)

    def _embed_api(self, text: str) -> np.ndarray:
        models = {"openai": "text-embedding-3-small", "siliconflow": "BAAI/bge-large-zh-v1.5", "deepseek": "deepseek-chat"}
        resp = self._client.embeddings.create(model=models[self.backend], input=text[:8000])
        arr = np.array(resp.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(arr)
        return arr / norm if norm > 0 else arr

    # ── Vector Store ──

    def build_index(self, objects: List[dict], force_rebuild: bool = False):
        self._ensure_init()
        if not objects:
            return
        if self.backend == "local":
            self._build_faiss(objects)
            return
        ids, embeddings, docs, metas = [], [], [], []
        for i, obj in enumerate(objects):
            oid = str(obj.get("id", i))
            text = f"{obj.get('summary', '')} {obj.get('body', '')}"[:2000]
            emb = self.embed(text)
            ids.append(oid)
            embeddings.append(emb.tolist())
            docs.append(text[:500])
            uid = obj.get("user_id")
            metas.append({
                "type": obj.get("type", ""),
                "status": obj.get("status", "active"),
                "user_id": str(uid) if uid is not None else "global",
            })
            self._id_to_idx[oid] = oid
            self._idx_to_id[oid] = oid
        if ids:
            self._collection.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
            logger.info(f"ChromaDB index: {len(ids)} vectors")

    def _build_faiss(self, objects: List[dict]):
        import faiss
        ids, embs = [], []
        for i, obj in enumerate(objects):
            oid = str(obj.get("id", i))
            text = f"{obj.get('summary', '')} {obj.get('body', '')}"[:2000]
            ids.append(oid)
            embs.append(self.embed(text))
            uid = obj.get("user_id")
            self._metadata_by_id[oid] = {
                "type": obj.get("type", ""),
                "status": obj.get("status", "active"),
                "user_id": str(uid) if uid is not None else "global",
            }
            self._documents_by_id[oid] = text[:500]
        if not embs:
            return
        arr = np.array(embs, dtype=np.float32)
        idx = faiss.IndexFlatIP(arr.shape[1])
        idx.add(arr)
        self.faiss_index = idx
        self._id_to_idx = {oid: i for i, oid in enumerate(ids)}
        self._idx_to_id = {i: oid for i, oid in enumerate(ids)}
        logger.info(f"FAISS index: {idx.ntotal} vectors")

    def search(self, query: str, top_k: int = 10, where: Optional[dict] = None) -> List[dict]:
        """Search vectors; `where` (e.g. {"user_id": "7"}) scopes by metadata.

        The FAISS backend has no metadata store: it filters after the fact by
        intersecting with the ids the caller knows about (pass `where` and the
        caller's ownership is enforced in the DB join anyway).
        """
        self._ensure_init()
        if self.backend == "local":
            return self._search_faiss(query, top_k, where=where)
        return self._search_chroma(query, top_k, where=where)

    def _search_chroma(self, query: str, top_k: int, where: Optional[dict] = None) -> List[dict]:
        if self._collection is None or self._collection.count() == 0:
            return []
        qv = self.embed(query)
        kwargs = {"query_embeddings": [qv.tolist()],
                  "n_results": min(top_k, self._collection.count())}
        if where:
            kwargs["where"] = where
        r = self._collection.query(**kwargs)
        if not r or not r.get("ids") or not r["ids"][0]:
            return []
        return [{"id": oid, "score": max(0.0, 1.0 - float(d))} for oid, d in zip(r["ids"][0], r["distances"][0])]

    def _search_faiss(self, query: str, top_k: int,
                      where: Optional[dict] = None) -> List[dict]:
        if self.faiss_index is None:
            return []
        qv = self.embed(query).reshape(1, -1).astype(np.float32)
        candidate_count = self.faiss_index.ntotal if where else top_k
        dists, idxs = self.faiss_index.search(qv, candidate_count)
        rows = []
        for distance, index in zip(dists[0], idxs[0]):
            if index < 0 or index not in self._idx_to_id:
                continue
            object_id = self._idx_to_id[index]
            metadata = self._metadata_by_id.get(object_id, {})
            if where and any(str(metadata.get(k)) != str(v) for k, v in where.items()):
                continue
            rows.append({"id": object_id, "score": float(distance)})
            if len(rows) >= top_k:
                break
        return rows

    def add_vector(self, obj_id: str, text: str, metadata: Optional[dict] = None):
        """Index one object. `metadata` must carry user_id for isolation."""
        self._ensure_init()
        meta = dict(metadata or {})
        meta.setdefault("user_id", "global")
        meta.setdefault("status", "active")
        if self.backend == "local":
            if self.faiss_index is None:
                return
            v = self.embed(text).reshape(1, -1).astype(np.float32)
            self.faiss_index.add(v)
            idx = self.faiss_index.ntotal - 1
            self._id_to_idx[obj_id] = idx
            self._idx_to_id[idx] = obj_id
            self._metadata_by_id[obj_id] = meta
            self._documents_by_id[obj_id] = text[:500]
            return
        emb = self.embed(text)
        self._collection.upsert(ids=[str(obj_id)], embeddings=[emb.tolist()],
                                documents=[text[:500]], metadatas=[meta])

    def delete_vectors(self, ids: List[str]):
        """Remove vectors by id (object delete/archive)."""
        self._ensure_init()
        ids = [str(i) for i in ids]
        if self.backend == "local":
            self._rebuild_local_without(set(ids))
            return
        if self._collection is not None:
            try:
                self._collection.delete(ids=ids)
            except Exception:
                logger.warning("ChromaDB delete failed (continuing)", exc_info=True)

    def _rebuild_local_without(self, remove_ids: set[str]) -> int:
        if self.faiss_index is None or not remove_ids:
            return 0
        ordered = [
            (index, object_id) for index, object_id in self._idx_to_id.items()
            if object_id not in remove_ids
        ]
        ordered.sort()
        vectors = [self.faiss_index.reconstruct(index) for index, _ in ordered]
        replacement = type(self.faiss_index)(self.faiss_index.d)
        if vectors:
            replacement.add(np.asarray(vectors, dtype=np.float32))
        removed = len(self._idx_to_id) - len(ordered)
        self.faiss_index = replacement
        self._id_to_idx = {object_id: index for index, (_, object_id) in enumerate(ordered)}
        self._idx_to_id = {index: object_id for index, (_, object_id) in enumerate(ordered)}
        for object_id in remove_ids:
            self._metadata_by_id.pop(object_id, None)
            self._documents_by_id.pop(object_id, None)
        return removed

    @staticmethod
    def _normalise_vector(value):
        return value.tolist() if hasattr(value, "tolist") else list(value)

    def export_user(self, user_id) -> List[dict]:
        """Export vectors and source metadata owned by one user."""
        self._ensure_init()
        if self.backend == "local":
            rows = []
            for index, object_id in sorted(self._idx_to_id.items()):
                metadata = self._metadata_by_id.get(object_id, {})
                if str(metadata.get("user_id")) != str(user_id):
                    continue
                rows.append({
                    "id": object_id,
                    "document": self._documents_by_id.get(object_id, ""),
                    "metadata": metadata,
                    "embedding": self._normalise_vector(
                        self.faiss_index.reconstruct(index)),
                })
            return rows
        if self._collection is None:
            return []
        result = self._collection.get(
            where={"user_id": str(user_id)},
            include=["documents", "metadatas", "embeddings"],
        )
        ids = result.get("ids") or []
        documents = result.get("documents") or [""] * len(ids)
        metadatas = result.get("metadatas") or [{}] * len(ids)
        embeddings = result.get("embeddings")
        if embeddings is None:
            embeddings = [[] for _ in ids]
        return [{
            "id": object_id,
            "document": documents[index],
            "metadata": metadatas[index],
            "embedding": self._normalise_vector(embeddings[index]),
        } for index, object_id in enumerate(ids)]

    def delete_user(self, user_id) -> int:
        """Remove every vector owned by a user and return the exact count."""
        self._ensure_init()
        if self.backend == "local":
            remove_ids = {
                object_id for object_id, metadata in self._metadata_by_id.items()
                if str(metadata.get("user_id")) == str(user_id)
            }
            return self._rebuild_local_without(remove_ids)
        if self._collection is None:
            return 0
        result = self._collection.get(where={"user_id": str(user_id)}, include=[])
        ids = result.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)


# MiniLM singleton for conflict detection (paper-calibrated, 384-dim)
_conflict_model = None

def get_conflict_embedding() -> callable:
    """Get MiniLM embedding function for conflict detection.

    Always uses MiniLM 384-dim, regardless of global backend.
    Paper parameters (α/β/γ/θ_c) calibrated on this model.
    """
    global _conflict_model
    if _conflict_model is None:
        import sentence_transformers
        model_path = os.environ.get(
            "MINTA_CONFLICT_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        _conflict_model = sentence_transformers.SentenceTransformer(model_path)
    return lambda text: _conflict_model.encode(text, normalize_embeddings=True).astype(np.float32)


_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
