"""Per-user vector export/deletion must be truthful for every backend."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.embedding_service import EmbeddingService


class FakeCollection:
    def __init__(self):
        self.deleted = []

    def get(self, where=None, include=None):
        assert where == {"user_id": "7"}
        return {
            "ids": ["a", "b"],
            "documents": ["one", "two"],
            "metadatas": [{"user_id": "7"}, {"user_id": "7"}],
            "embeddings": [[1.0, 0.0], [0.0, 1.0]],
        }

    def delete(self, ids=None, where=None):
        self.deleted.extend(ids or [])


def test_chroma_export_and_delete_report_exact_vectors():
    service = EmbeddingService("chromadb")
    service._initialized = True
    service._collection = FakeCollection()
    rows = service.export_user(7)
    assert [r["id"] for r in rows] == ["a", "b"]
    assert service.delete_user(7) == 2
    assert service._collection.deleted == ["a", "b"]


def test_local_delete_rebuilds_index_without_users_vectors():
    class FakeIndex:
        def __init__(self, dimension):
            self.d = dimension
            self._rows = []

        @property
        def ntotal(self):
            return len(self._rows)

        def add(self, rows):
            self._rows.extend(np.asarray(rows, dtype=np.float32))

        def reconstruct(self, index):
            return np.asarray(self._rows[index], dtype=np.float32)

    service = EmbeddingService("local")
    service._initialized = True
    service.faiss_index = FakeIndex(2)
    service.faiss_index.add(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    service._id_to_idx = {"mine": 0, "other": 1}
    service._idx_to_id = {0: "mine", 1: "other"}
    service._metadata_by_id = {
        "mine": {"user_id": "7"}, "other": {"user_id": "8"}}
    service._documents_by_id = {"mine": "private", "other": "keep"}

    assert service.delete_user(7) == 1
    assert service.faiss_index.ntotal == 1
    assert service._idx_to_id == {0: "other"}
    assert [r["id"] for r in service.export_user(8)] == ["other"]
