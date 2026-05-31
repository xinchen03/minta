"""Conflict Detector — lightweight version for public demo.

Uses default parameters. Calibrated values are in the private Minta-next repo.
"""
from __future__ import annotations
import json
import math
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional

import numpy as np

# Default parameters (safe for public demo, not calibrated)
ALPHA = 2.0
BETA = 1.0
GAMMA = 0.5
THETA_C = 0.45
THETA_R = 0.85

_NEGATION_EN = re.compile(
    r'\b(not|never|don\'t|do not|no longer|dislike|unlike|'
    r'cannot|can\'t|won\'t|will not|shouldn\'t|should not|'
    r'hardly|barely|scarcely|seldom|neither|nor|'
    r'without|except|instead of|rather than|'
    r'opposite|contrary)\b',
    re.IGNORECASE,
)
_NEGATION_ZH = re.compile(r'不|没|无|非|否|别|莫|勿|休|讨厌|不喜欢|不再|从不|绝不|永不')

THETA_S = 0.30


def check_negation_bypass(text_i: str, text_j: str) -> bool:
    if not text_i and not text_j:
        return False
    combined = (text_i or "") + " " + (text_j or "")
    return bool(_NEGATION_EN.search(combined) or _NEGATION_ZH.search(combined))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def cosine_similarity(emb_i: np.ndarray, emb_j: np.ndarray) -> float:
    return float(np.dot(emb_i, emb_j))


def cosine_distance(emb_i: np.ndarray, emb_j: np.ndarray) -> float:
    return 1.0 - cosine_similarity(emb_i, emb_j)


def parse_embedding(emb_str: Optional[str]) -> Optional[np.ndarray]:
    if not emb_str:
        return None
    try:
        arr = np.array(json.loads(emb_str), dtype=np.float32)
        return arr if len(arr) > 0 else None
    except (json.JSONDecodeError, ValueError):
        return None


def compute_conflict_prob(emb_i, emb_j, t_create_i, t_create_j) -> float:
    d_sem = cosine_distance(emb_i, emb_j)
    delta_days = abs((t_create_i - t_create_j).total_seconds()) / 86400.0
    z = GAMMA - ALPHA * d_sem + BETA * (delta_days / 365.0)
    return round(sigmoid(z), 6)
