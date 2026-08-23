"""Embedding service — ChromaDB (default) + FAISS (fallback).

Backends:
- chromadb (default): Persistent vector store, mpnet 768-dim, survives restart.
- local: FAISS in-memory index, MiniLM 384-dim, original py38 backend.
- openai / siliconflow / deepseek: API-based embeddings.

Public API unchanged:
    embed(text) -> np.ndarray
    embed_batch(texts) -> np.ndarray
    build_index(objects) -> None
    search(query, top_k) -> List[dict]
    add_vector(obj_id, text) -> None
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
        from chromadb.utils import embedding_functions

        model_path = os.environ.get("MINTA_EMBEDDING_MODEL", "D:/all-mpnet-base-v2")
        self._model = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_path,
        )
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
        model_path = os.environ.get("MINTA_EMBEDDING_MODEL", "D:/models/all-MiniLM-L6-v2")
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
                return np.array(self._model([text])[0], dtype=np.float32)
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
                return np.array(self._model(texts), dtype=np.float32)
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
            metas.append({"type": obj.get("type", ""), "status": obj.get("status", "active")})
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
        if not embs:
            return
        arr = np.array(embs, dtype=np.float32)
        idx = faiss.IndexFlatIP(arr.shape[1])
        idx.add(arr)
        self.faiss_index = idx
        self._id_to_idx = {oid: i for i, oid in enumerate(ids)}
        self._idx_to_id = {i: oid for i, oid in enumerate(ids)}
        logger.info(f"FAISS index: {idx.ntotal} vectors")

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        self._ensure_init()
        if self.backend == "local":
            return self._search_faiss(query, top_k)
        return self._search_chroma(query, top_k)

    def _search_chroma(self, query: str, top_k: int) -> List[dict]:
        if self._collection is None or self._collection.count() == 0:
            return []
        qv = self.embed(query)
        r = self._collection.query(query_embeddings=[qv.tolist()], n_results=min(top_k, self._collection.count()))
        if not r or not r.get("ids") or not r["ids"][0]:
            return []
        return [{"id": oid, "score": max(0.0, 1.0 - float(d))} for oid, d in zip(r["ids"][0], r["distances"][0])]

    def _search_faiss(self, query: str, top_k: int) -> List[dict]:
        if self.faiss_index is None:
            return []
        qv = self.embed(query).reshape(1, -1).astype(np.float32)
        dists, idxs = self.faiss_index.search(qv, top_k)
        return [{"id": self._idx_to_id[i], "score": float(d)} for d, i in zip(dists[0], idxs[0]) if i >= 0 and i in self._idx_to_id]

    def add_vector(self, obj_id: str, text: str):
        self._ensure_init()
        if self.backend == "local":
            if self.faiss_index is None:
                return
            v = self.embed(text).reshape(1, -1).astype(np.float32)
            self.faiss_index.add(v)
            idx = self.faiss_index.ntotal - 1
            self._id_to_idx[obj_id] = idx
            self._idx_to_id[idx] = obj_id
            return
        emb = self.embed(text)
        self._collection.upsert(ids=[str(obj_id)], embeddings=[emb.tolist()], documents=[text[:500]])


# MiniLM singleton for conflict detection (paper-calibrated, 384-dim)
_conflict_model = None

def get_conflict_embedding() -> callable:
    """Get MiniLM embedding function for conflict detection.

    Always uses MiniLM 384-dim, regardless of global backend.
    Paper parameters (α/β/γ/θ_c) calibrated on this model.
    """
    global _conflict_model
    if _conflict_model is None:
        from chromadb.utils import embedding_functions
        _conflict_model = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="D:/models/all-MiniLM-L6-v2",
        )
    return lambda text: _conflict_model([text])[0]


_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
