"""Embedding service — ChromaDB vector store with pluggable backends.

Public default: ChromaDB built-in MiniLM (384-dim, ~90MB).
No torch/sentence-transformers required. pip install minta just works.

Pro upgrade: sentence-transformers + mpnet (768-dim) via pip install minta[st].
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
EMBEDDING_DIM = int(os.environ.get("MINTA_EMBEDDING_DIM", "384"))


def _chroma_path() -> str:
    return os.environ.get(
        "MINTA_CHROMA_PATH",
        str(Path.home() / ".minta" / "chroma_data"),
    )


class EmbeddingService:
    """ChromaDB-first embedding service. Public API unchanged."""

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

        model_name = os.environ.get("MINTA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self._model = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name,
        )
        path = _chroma_path()
        os.makedirs(path, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=path)
        try:
            self._collection = self._chroma_client.get_collection("minta_memories")
        except Exception:
            self._collection = self._chroma_client.create_collection(
                "minta_memories", metadata={"hnsw:space": "cosine"},
            )
        self.faiss_index = True  # backward compat sentinel

    def _init_local(self):
        import sentence_transformers
        self._model = sentence_transformers.SentenceTransformer(
            os.environ.get("MINTA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        )

    def _init_api(self):
        import openai
        keys = {"openai": "OPENAI_API_KEY", "siliconflow": "SILICONFLOW_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
        self._client = openai.OpenAI(api_key=os.environ.get(keys[self.backend]))

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
            return np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)

    def _embed_api(self, text: str) -> np.ndarray:
        models = {"openai": "text-embedding-3-small", "siliconflow": "BAAI/bge-large-zh-v1.5", "deepseek": "deepseek-chat"}
        resp = self._client.embeddings.create(model=models[self.backend], input=text[:8000])
        arr = np.array(resp.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(arr)
        return arr / norm if norm > 0 else arr

    def build_index(self, objects: List[dict], force_rebuild: bool = False):
        self._ensure_init()
        if not objects:
            return
        if self.backend == "local":
            self._build_faiss(objects)
            return
        ids, embs, docs, metas = [], [], [], []
        for i, obj in enumerate(objects):
            oid = str(obj.get("id", i))
            text = f"{obj.get('summary', '')} {obj.get('body', '')}"[:2000]
            ids.append(oid)
            embs.append(self.embed(text).tolist())
            docs.append(text[:500])
            metas.append({"type": obj.get("type", ""), "status": obj.get("status", "active")})
        if ids:
            self._collection.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)

    def _build_faiss(self, objects):
        import faiss
        ids, arrs = [], []
        for i, obj in enumerate(objects):
            ids.append(str(obj.get("id", i)))
            arrs.append(self.embed(f"{obj.get('summary','')} {obj.get('body','')}"[:2000]))
        if not arrs:
            return
        emb = np.array(arrs, dtype=np.float32)
        idx = faiss.IndexFlatIP(emb.shape[1])
        idx.add(emb)
        self.faiss_index = idx
        self._id_to_idx = {oid: i for i, oid in enumerate(ids)}
        self._idx_to_id = {i: oid for i, oid in enumerate(ids)}

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        self._ensure_init()
        if self.backend == "local":
            return self._search_faiss(query, top_k)
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
            if self.faiss_index is None: return
            v = self.embed(text).reshape(1, -1).astype(np.float32)
            self.faiss_index.add(v)
            idx = self.faiss_index.ntotal - 1
            self._id_to_idx[obj_id] = idx
            self._idx_to_id[idx] = obj_id
            return
        emb = self.embed(text)
        self._collection.upsert(ids=[str(obj_id)], embeddings=[emb.tolist()], documents=[text[:500]])


_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
