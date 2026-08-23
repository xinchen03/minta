"""Conflict Detector — logistic-model contradiction detection.

Implements Eq.5 from the Minta paper:
    P_conflict(c_i, c_j) = σ(γ - α·d(e_i, e_j) + β·Δ_ij)

Four-gate filtering (negation-bypass + redundancy + probability + staleness) per Section 4.3.
"""
from __future__ import annotations
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Calibrated parameters (grid search on 30 Task-B templates, 5-fold CV F1=0.683)
ALPHA = 2.10
BETA = 1.30
GAMMA = 0.40
THETA_C = 0.46       # decision threshold for conflict classification
THETA_R = 0.85        # redundancy threshold (cosine similarity)

# Negation bypass — lexical patterns indicating polarity reversal (Section 4.5, B_ij)
# English: word-boundary patterns
_NEGATION_EN = re.compile(
    r'\b(not|never|don\'t|do not|no longer|dislike|unlike|'
    r'cannot|can\'t|won\'t|will not|shouldn\'t|should not|'
    r'hardly|barely|scarcely|seldom|neither|nor|'
    r'without|except|instead of|rather than|'
    r'opposite|contrary|reverse|inverse)\b',
    re.IGNORECASE,
)
# Chinese/Japanese: no \b needed (CJK characters are continuous)
_NEGATION_ZH = re.compile(
    r'不|没|无|非|否|别|莫|勿|休|'
    r'讨厌|不喜欢|不再|从不|绝不|永不',
)

# Staleness gate — import from decay engine
from services.decay_engine import THETA_S, compute_retention, initial_relevance_from_confidence


def check_negation_bypass(text_i: str, text_j: str) -> bool:
    """Check if either entry contains negation markers (B_ij gate).

    When two entries are semantically similar but one contains negation,
    they are likely contradictory rather than redundant.
    E.g., "I like coffee" vs "I do not like coffee" → B_ij = 1.

    Returns True if negation is detected in either text.
    """
    if not text_i and not text_j:
        return False
    combined = (text_i or "") + " " + (text_j or "")
    return bool(
        _NEGATION_EN.search(combined) or
        _NEGATION_ZH.search(combined)
    )


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def cosine_similarity(emb_i: np.ndarray, emb_j: np.ndarray) -> float:
    """Cosine similarity of two L2-normalized embedding vectors."""
    return float(np.dot(emb_i, emb_j))


def cosine_distance(emb_i: np.ndarray, emb_j: np.ndarray) -> float:
    """Cosine distance d = 1 - sim ∈ [0, 2]."""
    return 1.0 - cosine_similarity(emb_i, emb_j)


def parse_embedding(emb_str: Optional[str]) -> Optional[np.ndarray]:
    """Parse JSON embedding string to numpy array."""
    if not emb_str:
        return None
    try:
        arr = np.array(json.loads(emb_str), dtype=np.float32)
        if len(arr) == 0:
            return None
        return arr
    except (json.JSONDecodeError, ValueError):
        return None


def compute_conflict_prob(
    emb_i: np.ndarray,
    emb_j: np.ndarray,
    t_create_i: datetime,
    t_create_j: datetime,
) -> float:
    """Compute P_conflict for a pair of context objects.

    P = σ(γ - α·d(e_i, e_j) + β·Δ_ij)
    Δ_ij = |t_create_i - t_create_j| / 365  (years)
    """
    d_sem = cosine_distance(emb_i, emb_j)
    delta_days = abs((t_create_i - t_create_j).total_seconds()) / 86400.0
    delta_years = delta_days / 365.0

    z = GAMMA - ALPHA * d_sem + BETA * delta_years
    return round(sigmoid(z), 6)


def detect_conflicts(
    objects: List[Dict],
    now: Optional[datetime] = None,
    graph_edges: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Detect active contradictions in a pool of context objects.

    Five-gate filter for each pair (i, j):
    0. Negation bypass (B_ij): if negation markers found, bypass redundancy gate
    1. Redundancy gate: sim(e_i, e_j) ≤ θ_r (skip near-duplicates unless B_ij=1)
    2. Probability gate: P_conflict > θ_c (adjusted by neighbor consensus when graph_edges provided)
    3. Staleness gate: both entries still relevant (R_i, R_j ≥ θ_s)

    MMA-style neighbor consensus (2026-07-08): when graph_edges is provided,
    P_conflict is adjusted based on each object's neighborhood support.
    Objects with weak neighbor consensus have amplified conflict probability.

    Args:
        objects: List of dicts with keys: id, embedding_384, created_at,
                 last_used_at, updated_at, confidence, type, status,
                 title, summary, body (for negation detection).
        now: Current time.
        graph_edges: Optional list of dicts with source_id, target_id, edge_type.

    Returns:
        List of conflict findings with object_ids, probability, and suggestion.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Pre-compute embeddings and retention
    parsed: List[Dict] = []
    for obj in objects:
        emb = parse_embedding(obj.get("embedding_384"))
        if emb is None:
            continue

        created = obj.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if created is None:
            created = now

        last_access = obj.get("last_used_at") or obj.get("updated_at") or created
        if isinstance(last_access, str):
            last_access = datetime.fromisoformat(last_access.replace("Z", "+00:00"))

        r0 = initial_relevance_from_confidence(obj.get("confidence", 3))
        retention = compute_retention(
            initial_relevance=r0,
            last_access=last_access,
            context_type=obj.get("type", "task_note"),
            now=now,
        )

        parsed.append({
            "id": obj.get("id"),
            "title": obj.get("title", ""),
            "body": obj.get("body", "") or obj.get("summary", ""),
            "emb": emb,
            "created_at": created,
            "retention": retention,
        })

    n = len(parsed)
    findings = []
    for i in range(n):
        for j in range(i + 1, n):
            pi, pj = parsed[i], parsed[j]

            # Gate 0: Negation bypass (B_ij) — check before redundancy gate
            b_ij = check_negation_bypass(
                (pi.get("title") or "") + " " + (pi.get("body") or ""),
                (pj.get("title") or "") + " " + (pj.get("body") or ""),
            )

            # Gate 1: Redundancy — skip near-duplicates unless negation detected
            sim = cosine_similarity(pi["emb"], pj["emb"])
            if sim > THETA_R and not b_ij:
                continue

            # Gate 2: Conflict probability (with optional neighbor consensus)
            consensus_result = conflict_with_consensus(
                {"id": pi["id"]}, {"id": pj["id"]},
                pi["emb"], pj["emb"],
                pi["created_at"], pj["created_at"],
                graph_edges=graph_edges,
            )
            p_conf = consensus_result["p_adjusted"]
            p_conf_base = consensus_result["p_conflict"]
            if p_conf <= THETA_C:
                continue

            # Gate 3: Staleness — both must be relevant
            if pi["retention"] < THETA_S or pj["retention"] < THETA_S:
                continue

            # Resolve conflict (soft-marking, Mem0-inspired)
            resolution = resolve_conflict(
                {"id": pi["id"], "title": pi["title"], "body": pi.get("body", ""),
                 "created_at": str(pi["created_at"])},
                {"id": pj["id"], "title": pj["title"], "body": pj.get("body", ""),
                 "created_at": str(pj["created_at"])},
                p_conf,
            )

            findings.append({
                "type": "conflict",
                "severity": "high",
                "object_ids": [pi["id"], pj["id"]],
                "titles": [pi["title"], pj["title"]],
                "conflict_probability": round(p_conf, 4),
                "conflict_probability_base": round(p_conf_base, 4),
                "cosine_similarity": round(sim, 4),
                "consensus": {
                    pi["id"]: consensus_result["consensus_i"],
                    pj["id"]: consensus_result["consensus_j"],
                },
                "resolution": resolution["resolution"],
                "winner_id": resolution["winner_id"],
                "loser_id": resolution["loser_id"],
                "suggestion": (
                    f"「{pi['title']}」与「{pj['title']}」可能矛盾 "
                    f"(P_conflict={p_conf:.3f} > θ_c={THETA_C})。"
                    f"Resolution: {resolution['resolution']} — {resolution['reason']}"
                ),
            })

    findings.sort(key=lambda f: -f["conflict_probability"])
    return findings[:20]


def resolve_conflict(
    obj_i: Dict,
    obj_j: Dict,
    conflict_prob: float,
) -> Dict:
    """Determine conflict resolution without LLM.

    Mem0-inspired soft marking: superseded facts are marked invalid
    rather than physically deleted, preserving history for temporal reasoning.

    Decision rules (all local, no API):
    1. If one fact explicitly negates the other → negator wins, negated is superseded
    2. If timestamps differ by > 7 days → newer wins (more current info)
    3. If confidence differs → higher confidence wins
    4. Default: both marked as "active" (ambiguous, needs human review)

    Returns:
        dict with winner_id, loser_id, resolution, reason
    """
    text_i = (obj_i.get("title", "") + " " + (obj_i.get("body", "") or obj_i.get("summary", ""))).strip()
    text_j = (obj_j.get("title", "") + " " + (obj_j.get("body", "") or obj_j.get("summary", ""))).strip()

    # Rule 1: Negation bypass — check which one negates the other
    neg_i = bool(_NEGATION_EN.search(text_i) or _NEGATION_ZH.search(text_i))
    neg_j = bool(_NEGATION_EN.search(text_j) or _NEGATION_ZH.search(text_j))

    if neg_i and not neg_j:
        return {
            "winner_id": obj_i.get("id"),
            "loser_id": obj_j.get("id"),
            "resolution": "superseded",
            "reason": f"Fact {obj_i.get('id')} contains negation and overrides {obj_j.get('id')}",
        }
    if neg_j and not neg_i:
        return {
            "winner_id": obj_j.get("id"),
            "loser_id": obj_i.get("id"),
            "resolution": "superseded",
            "reason": f"Fact {obj_j.get('id')} contains negation and overrides {obj_i.get('id')}",
        }

    # Rule 2: Timestamp-based (newer > 7 days difference wins)
    t_i = _parse_time(obj_i.get("created_at"))
    t_j = _parse_time(obj_j.get("created_at"))
    if t_i and t_j:
        delta_days = abs((t_i - t_j).total_seconds()) / 86400.0
        if delta_days > 7:
            if t_i > t_j:
                return {
                    "winner_id": obj_i.get("id"),
                    "loser_id": obj_j.get("id"),
                    "resolution": "superseded",
                    "reason": f"Newer fact ({delta_days:.0f}d gap) supersedes older",
                }
            else:
                return {
                    "winner_id": obj_j.get("id"),
                    "loser_id": obj_i.get("id"),
                    "resolution": "superseded",
                    "reason": f"Newer fact ({delta_days:.0f}d gap) supersedes older",
                }

    # Rule 3: Confidence-based
    conf_i = obj_i.get("confidence", 3)
    conf_j = obj_j.get("confidence", 3)
    if isinstance(conf_i, (int, float)) and isinstance(conf_j, (int, float)):
        if conf_i > conf_j + 1:
            return {
                "winner_id": obj_i.get("id"),
                "loser_id": obj_j.get("id"),
                "resolution": "superseded",
                "reason": f"Higher confidence ({conf_i} vs {conf_j})",
            }
        if conf_j > conf_i + 1:
            return {
                "winner_id": obj_j.get("id"),
                "loser_id": obj_i.get("id"),
                "resolution": "superseded",
                "reason": f"Higher confidence ({conf_j} vs {conf_i})",
            }

    # Default: ambiguous
    return {
        "winner_id": None,
        "loser_id": None,
        "resolution": "ambiguous",
        "reason": f"Cannot auto-resolve (P_conflict={conflict_prob:.3f}). Human review required.",
    }


def resolve_and_persist(
    winner_id: str,
    loser_id: str,
    resolution: str,
    reason: str,
    db_session=None,
) -> bool:
    """Commit conflict resolution to the database.

    Sets loser status to 'stale', records winner reference in loser's tags.
    Graphiti-inspired: old facts are marked invalid, not deleted.

    Returns True if DB update succeeded.
    """
    if db_session is None:
        logger.warning("No DB session provided — resolution not persisted")
        return False

    try:
        from models.context_object import ContextObject
        import json as _json

        loser = db_session.query(ContextObject).filter(
            ContextObject.id == loser_id
        ).first()

        if loser:
            loser.status = "stale"
            # Record resolution metadata in tags
            tags = loser.tags or []
            if isinstance(tags, str):
                try:
                    tags = _json.loads(tags)
                except Exception:
                    tags = []
            tags.append({
                "_resolution": resolution,
                "_superseded_by": winner_id,
                "_reason": reason,
                "_resolved_at": datetime.now(timezone.utc).isoformat(),
            })
            loser.tags = tags
            db_session.commit()
            logger.info(f"Persisted: {loser_id} marked stale, superseded by {winner_id}")
            return True

    except Exception as e:
        logger.error(f"Failed to persist resolution: {e}")
        if db_session:
            db_session.rollback()
    return False


def _parse_time(val) -> Optional[datetime]:
    """Parse a datetime value from various formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            pass
    return None


# ── MMA-style Neighbor Consensus (2026 integration) ──

def neighbor_consensus_score(
    obj_id: str,
    graph_edges: List[Dict],
    *,
    min_neighbors: int = 2,
    default_score: float = 0.5,
) -> float:
    """Compute reliability score from graph neighborhood consensus (inspired by MMA).

    For each edge where this object appears (as source or target):
    - corroborates edges → +0.1 each
    - contradicts edges → −0.15 each
    - consults edges → +0.05 each

    Clamped to [0, 1]. Falls back to default_score if < min_neighbors edges.

    Args:
        obj_id: Context object ID to evaluate.
        graph_edges: List of dicts with keys: source_id, target_id, edge_type.
        min_neighbors: Minimum edges required for reliable consensus.
        default_score: Score returned when insufficient neighbors.

    Returns:
        Consensus score ∈ [0, 1].
    """
    score = 0.0
    edge_count = 0
    for edge in graph_edges:
        src = edge.get("source_id") or edge.get("sourceId") or edge.get("a_id")
        tgt = edge.get("target_id") or edge.get("targetId") or edge.get("b_id")
        etype = edge.get("edge_type") or edge.get("type") or edge.get("edgeType", "")

        if obj_id not in (src, tgt):
            continue
        edge_count += 1

        if etype in ("corroborates", "supports", "confirms"):
            score += 0.10
        elif etype in ("contradicts", "conflicts", "refutes"):
            score -= 0.15
        elif etype in ("consults", "references", "related_to"):
            score += 0.05

    if edge_count < min_neighbors:
        return default_score

    return max(0.0, min(1.0, 0.5 + score))


def conflict_with_consensus(
    obj_i: Dict,
    obj_j: Dict,
    emb_i: np.ndarray,
    emb_j: np.ndarray,
    t_create_i: datetime,
    t_create_j: datetime,
    graph_edges: List[Dict] = None,
) -> Dict:
    """Compute conflict probability with neighbor consensus adjustment.

    P_adjusted = P_conflict × (1 + 0.2 × (1 − consensus_i)) × (1 + 0.2 × (1 − consensus_j))

    When both objects have strong neighbor support (consensus ≈ 1),
    the adjustment is negligible. When either has weak support,
    conflict probability is amplified (less reliable info → higher conflict risk).

    Returns dict with p_conflict, p_adjusted, consensus_i, consensus_j.
    """
    p_conf = compute_conflict_prob(emb_i, emb_j, t_create_i, t_create_j)

    if graph_edges is None:
        graph_edges = []

    consensus_i = neighbor_consensus_score(obj_i.get("id", ""), graph_edges)
    consensus_j = neighbor_consensus_score(obj_j.get("id", ""), graph_edges)

    # Amplify conflict probability when either object has weak neighborhood support
    adjustment = (1.0 + 0.2 * (1.0 - consensus_i)) * (1.0 + 0.2 * (1.0 - consensus_j))
    p_adjusted = min(1.0, p_conf * adjustment)

    return {
        "p_conflict": round(p_conf, 6),
        "p_adjusted": round(p_adjusted, 6),
        "consensus_i": round(consensus_i, 4),
        "consensus_j": round(consensus_j, 4),
        "adjustment_factor": round(adjustment, 4),
    }
