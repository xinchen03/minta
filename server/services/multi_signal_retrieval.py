"""Multi-signal retrieval: ChromaDB semantic + BM25 keyword + entity + temporal.

Four-channel reciprocal rank fusion (RRF).
Distilled from Mem0 v3: semantic + BM25 + entity signals fused with RRF.
Extended with temporal boost from temporal_resolver and entity linking.
"""
from __future__ import annotations
import logging
from typing import List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

from services.temporal_resolver import has_time_expression, resolve_time_range
from services.entity_linker import get_entity_keywords, entity_overlap_score
from services.reranker import rerank, is_available as reranker_available


class MultiSignalRetrieval:
    """Four-channel retrieval with RRF fusion.

    Channels: semantic (ChromaDB) + keyword (BM25) + entity (flashtext) + temporal.

    Usage:
        from services.embedding_service import get_embedding_service
        retriever = MultiSignalRetrieval(embedding_service=get_embedding_service())
        retriever.index(context_objects)
        results = retriever.retrieve("user query", top_k=10)
    """

    def __init__(self, embedding_service=None, context_objects: Optional[list] = None, embedding_fn=None):
        self._embedding_service = embedding_service
        self.embedding_fn = embedding_fn or (embedding_service.embed if embedding_service else None)
        self._objects: List[dict] = []
        self._bm25 = None
        self._entity_index: dict = {}  # entity_name → [obj_ids]
        if context_objects:
            self.index(context_objects)

    def index(self, objects: List[dict]) -> None:
        """Index objects for all retrieval channels."""
        self._objects = objects
        # BM25
        if BM25_AVAILABLE and objects:
            try:
                corpus = [self._tokenize(o.get("summary","") + " " + o.get("body","")) for o in objects]
                self._bm25 = BM25Okapi(corpus)
            except Exception as e:
                logger.warning(f"BM25 index failed: {e}")
        # Entity index
        self._entity_index = {}
        for i, obj in enumerate(objects):
            oid = obj.get("id", str(i))
            text = f"{obj.get('summary','')} {obj.get('body','')}"
            entities = get_entity_keywords(text)
            for ent in entities:
                self._entity_index.setdefault(ent.lower(), []).append(oid)

    def _tokenize(self, text: str) -> List[str]:
        import re
        tokens = []
        for part in re.split(r'[a-zA-Z]+', text):
            if part.strip():
                tokens.extend(re.findall(r'[一-鿿]', part))
                for token in part.split():
                    token = re.sub(r'[^\w]', '', token)
                    if token: tokens.append(token.lower())
        for match in re.finditer(r'[a-zA-Z]+', text):
            tokens.append(match.group().lower())
        return tokens

    def retrieve(self, query: str, top_k: int = 10,
                 weights: Tuple[float, float, float, float] = None,
                 use_rerank: bool = False) -> List[dict]:
        """Multi-signal retrieval with weighted RRF fusion.

        Default weights tuned for recall (Mem0-inspired):
            semantic=0.40, keyword=0.25, entity=0.20, temporal=0.15
        """
        if weights is None:
            weights = (0.40, 0.25, 0.20, 0.15)

        n = max(top_k * 3, 30)
        result_lists: List[List[Tuple[str, float]]] = []

        # Channel 1: Semantic (ChromaDB)
        result_lists.append(self._semantic_search(query, n))
        # Channel 2: Keyword (BM25)
        result_lists.append(self._keyword_search(query, n))
        # Channel 3: Entity (flashtext overlap)
        result_lists.append(self._entity_search(query, n))
        # Channel 4: Temporal boost
        result_lists.append(self._temporal_boost(query, n))
        # Channel 5: Person name boost (distilled from MemPal)
        result_lists.append(self._person_name_boost(query, n))
        # Channel 6: Quoted phrase boost (distilled from MemPal)
        result_lists.append(self._quoted_phrase_boost(query, n))

        # Extend weights for 6 channels
        if len(weights) < 6:
            weights = tuple(list(weights) + [0.08, 0.07][:6 - len(weights)])

        results = self._rrf_fusion(result_lists, weights[:6], top_k * 2)  # extra candidates for rerank

        # Cross-Encoder reranking (optional, zero LLM cost)
        if use_rerank and reranker_available():
            return rerank(query, results, top_k=top_k)

        return results[:top_k]

    def _semantic_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        if self._embedding_service is None:
            return []
        try:
            raw = self._embedding_service.search(query, top_k=top_k)
            return [(r["id"], r["score"]) for r in raw]
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    def _keyword_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        if self._bm25 is None:
            return []
        try:
            tokens = self._tokenize(query)
            if not tokens: return []
            scores = self._bm25.get_scores(tokens)
            indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            max_s = indexed[0][1] if indexed else 1.0
            return [(self._objects[idx].get("id", str(idx)), s / max(max_s, 1.0))
                    for idx, s in indexed[:top_k] if s > 0]
        except Exception as e:
            logger.warning(f"Keyword search failed: {e}")
            return []

    def _entity_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Entity overlap search using flashtext-extracted entities."""
        query_entities = get_entity_keywords(query)
        if not query_entities:
            # Fallback: tag overlap (original behavior)
            return self._tag_overlap_search(query, top_k)

        scored = defaultdict(float)
        for qe in query_entities:
            for doc_ent, obj_ids in self._entity_index.items():
                if qe.lower() in doc_ent or doc_ent in qe.lower():
                    boost = 1.0 if qe.lower() == doc_ent else 0.7
                    for oid in obj_ids:
                        scored[oid] += boost

        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        max_s = ranked[0][1] if ranked else 1.0
        return [(oid, s / max_s) for oid, s in ranked[:top_k]]

    def _tag_overlap_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Fallback: original tag overlap."""
        qt = set(self._tokenize(query))
        if not qt: return []
        results = []
        for i, obj in enumerate(self._objects):
            tags = obj.get("tags", [])
            if isinstance(tags, list):
                tt = set()
                for tag in tags:
                    tt.update(self._tokenize(str(tag)))
                overlap = len(qt & tt)
                if overlap > 0:
                    results.append((obj.get("id", str(i)), overlap / max(len(qt), 1)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _temporal_boost(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Boost results with temporal proximity if query has time expressions."""
        if not has_time_expression(query):
            return []
        time_range = resolve_time_range(query)
        if time_range is None:
            return []

        start, end = time_range
        results = []
        for obj in self._objects:
            updated = obj.get("updated_at") or obj.get("created_at")
            if updated is None:
                continue
            try:
                from datetime import datetime
                if isinstance(updated, str):
                    updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if start <= updated.replace(tzinfo=None) <= end:
                    # Closer to start = higher score
                    proximity = max(0, 1 - abs((updated.replace(tzinfo=None) - start).days) / 90)
                    results.append((obj.get("id", str(0)), proximity))
            except Exception:
                pass
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _person_name_boost(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Boost sessions mentioning person names from query (distilled from MemPal v4)."""
        import re
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b', query)
        if not names:
            return []
        results = []
        for obj in self._objects:
            text = obj.get("summary", "") + " " + obj.get("body", "")
            boost = sum(0.4 for name in names if name.lower() in text.lower())
            if boost > 0:
                results.append((obj.get("id", ""), min(boost, 1.0)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _quoted_phrase_boost(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Boost sessions with exact quoted phrases (distilled from MemPal v4)."""
        import re
        phrases = re.findall(r"['\"]([^'\"]{3,})['\"]", query)
        if not phrases:
            return []
        results = []
        for obj in self._objects:
            text = obj.get("summary", "") + " " + obj.get("body", "")
            boost = sum(0.6 for p in phrases if p.lower() in text.lower())
            if boost > 0:
                results.append((obj.get("id", ""), min(boost, 1.0)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _rrf_fusion(self, result_lists: List[List[Tuple[str, float]]],
                    weights: Tuple[float, float, float, float], top_k: int) -> List[dict]:
        """Weighted reciprocal rank fusion (k=60)."""
        rrf: dict = defaultdict(float)
        k = 60
        for ch_idx, results in enumerate(result_lists):
            w = weights[ch_idx] if ch_idx < len(weights) else 0
            for rank, (oid, _) in enumerate(results):
                rrf[oid] += w / (k + rank + 1)

        sorted_ids = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
        result = []
        for oid, score in sorted_ids[:top_k]:
            obj = next((o for o in self._objects if o.get("id") == oid), None)
            if obj:
                entry = dict(obj)
                entry["_fused_score"] = round(score, 4)
                result.append(entry)
        return result
