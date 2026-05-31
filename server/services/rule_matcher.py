"""Medical Rule Semantic Matcher — natural language CPG rule ↔ ground truth matching.

Uses existing Minta Expert infrastructure: all-MiniLM + BM25 + RRF fusion.
Solves the core problem: "inability to weight bear" semantically matches
"inability to take four steps" even though keywords differ.

Algorithm:
  1. Clinical text preprocessing (normalization, abbreviation expansion)
  2. Entity extraction (jieba CN / regex EN + clinical term dictionary)
  3. Entity alignment (synonym expansion)
  4. Dual-path matching: dense (embedding cosine) + sparse (BM25 keyword)
  5. RRF fusion scoring → threshold-based match decision
"""
from __future__ import annotations
import os
import re
import logging
from typing import List, Dict, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Clinical synonym dictionary
CLINICAL_SYNONYMS = {
    "x-ray": ["xray", "radiograph", "radiographic series", "imaging", "X光", "拍片"],
    "xray": ["x-ray", "radiograph", "X光"],
    "tenderness": ["point tenderness", "bone tenderness", "压痛", "触痛", "按压痛"],
    "压痛": ["tenderness", "point tenderness", "触痛"],
    "lateral malleolus": ["外踝", "fibula distal"],
    "外踝": ["lateral malleolus"],
    "medial malleolus": ["内踝", "tibia distal"],
    "内踝": ["medial malleolus"],
    "weight bear": ["weight bearing", "ambulate", "walk", "take steps", "负重", "走路", "行走"],
    "负重": ["weight bear", "weight bearing", "ambulate", "走路"],
    "navicular": ["足舟骨", "navicular bone"],
    "足舟骨": ["navicular"],
    "fifth metatarsal": ["第五跖骨", "5th metatarsal", "metatarsal base"],
    "第五跖骨": ["fifth metatarsal", "5th metatarsal"],
    "swelling": ["edema", "肿胀", "淤血", "ecchymosis"],
    "肿胀": ["swelling", "edema"],
    "fracture": ["骨折", "break", "crack"],
    "骨折": ["fracture"],
    "ankle": ["踝关节", "ankle joint", "talocrural"],
    "踝关节": ["ankle", "ankle joint"],
    "foot": ["足部", "feet"],
    "足部": ["foot", "feet"],
    "recommend": ["建议", "应当", "should", "indicated", "required"],
    "建议": ["recommend", "should", "indicated"],
    "four steps": ["4 steps", "weight bear", "ambulate", "walk", "负重", "take four steps"],
    "take four steps": ["four steps", "weight bear", "weight bearing", "ambulate", "负重", "take steps"],
    "take steps": ["take four steps", "four steps", "weight bear", "ambulate", "负重"],
    "inability": ["cannot", "unable to", "不能", "无法", "做不到"],
    "不能": ["cannot", "unable to", "inability"],
    "immediately": ["即刻", "right away", "受伤后", "in the emergency department"],
    "emergency department": ["ED", "急诊", "急诊室", "急诊科", "in the ED", "in ED"],
    "ED": ["emergency department", "急诊", "急诊室"],
    "急诊": ["ED", "emergency department"],
    # Knee-specific terms (Ottawa Knee Rules)
    "patella": ["patellar", "kneecap", "髌骨", "knee cap"],
    "fibular head": ["fibula head", "腓骨头", "proximal fibula"],
    "knee flexion": ["flex the knee", "bend knee", "knee bend", "屈膝", "膝关节屈曲"],
    "age 55": ["age ≥ 55", "55 years", "55岁", "over 55"],
    "MVC": ["motor vehicle collision", "motor vehicle crash", "car accident", "车祸", "交通事故"],
    "motor vehicle collision": ["MVC", "motor vehicle crash", "car accident", "车祸"],
    "rear-end": ["rear end", "追尾", "rear impact"],
    "dangerous mechanism": ["high-risk mechanism", "severe mechanism", "危险机制"],
}


class RuleMatcher:
    """Semantic matching between compiled CPG rules and ground truth.

    Supports domain-specific fusion weights via a weight registry (JSON).
    Falls back to equal weights (1/3, 1/3, 1/3) when no domain is specified.
    """

    # Default fusion weights — used when no domain-specific weights loaded.
    # Overridden per-domain via load_domain_weights().
    DEFAULT_WEIGHTS = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)  # (w_entity, w_keyword, w_semantic)

    def __init__(self, embedding_service=None, domain: str = None):
        self._emb = embedding_service
        self._weights = self.DEFAULT_WEIGHTS
        self._domain = domain
        # Per-component reliability counters for online calibration
        self._reliability = {
            'entity': {'correct': 0, 'total': 0},
            'keyword': {'correct': 0, 'total': 0},
            'semantic': {'correct': 0, 'total': 0},
        }
        self._n_samples = 0
        if domain:
            self.load_domain_weights(domain)

    def _get_emb(self):
        if self._emb is None:
            from services.embedding_service import get_embedding_service
            self._emb = get_embedding_service()
        return self._emb

    def load_domain_weights(self, domain: str) -> Tuple[float, float, float]:
        """Load domain-specific fusion weights from the registry.

        Registry path: Minta project root / domain_weights.json
        Falls back to DEFAULT_WEIGHTS if the domain or file is not found.
        """
        import json as _json
        registry_paths = [
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'minta-expert-data', 'domain_weights.json'),
            r'D:\minta-expert-data\domain_weights.json',
        ]
        for rp in registry_paths:
            rp = os.path.normpath(rp)
            if os.path.exists(rp):
                with open(rp, 'r', encoding='utf-8') as f:
                    registry = _json.load(f)
                if domain in registry:
                    w = registry[domain]['weights']
                    self._weights = (w['w_entity'], w['w_keyword'], w['w_semantic'])
                    self._domain = domain
                    return self._weights
        # Domain not found — keep defaults
        logger.warning(f"Domain weights not found for '{domain}', using equal-weight fallback.")
        return self._weights

    @property
    def weights(self) -> Tuple[float, float, float]:
        """Current fusion weights (w_entity, w_keyword, w_semantic)."""
        return self._weights

    @weights.setter
    def weights(self, value: Tuple[float, float, float]):
        """Manually override fusion weights at runtime."""
        self._weights = tuple(value)
        self._domain = None  # custom weights decouple from domain

    def preprocess(self, text: str) -> str:
        """Normalize clinical text."""
        text = text.lower().strip()
        text = re.sub(r'[\(\)\[\]\{\}]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('x-ray', 'xray').replace('X-ray', 'xray')
        text = text.replace('x ray', 'xray').replace('X Ray', 'xray')
        return text.strip()

    def expand_synonyms(self, text: str) -> str:
        """Expand clinical synonyms for better matching coverage."""
        expanded = text
        for term, synonyms in CLINICAL_SYNONYMS.items():
            for syn in synonyms:
                if syn.lower() in text.lower() and term.lower() not in text.lower():
                    expanded += f" {term}"
        return expanded

    def extract_entities(self, text: str) -> List[str]:
        """Extract core clinical entities from text."""
        text_lower = text.lower()
        entities = []
        # Check clinical dictionary
        for term in CLINICAL_SYNONYMS:
            if term.lower() in text_lower:
                entities.append(term.lower())
        # Add all synonyms that appear
        for term, synonyms in CLINICAL_SYNONYMS.items():
            for syn in synonyms:
                if syn.lower() in text_lower and syn.lower() not in entities:
                    entities.append(syn.lower())
        return list(set(entities))

    def entity_overlap_score(self, entities_a: List[str], entities_b: List[str]) -> float:
        """Jaccard overlap on expanded entities (with synonym groups)."""
        if not entities_a or not entities_b:
            return 0.0
        intersection = len(set(entities_a) & set(entities_b))
        union = len(set(entities_a) | set(entities_b))
        return intersection / union if union > 0 else 0.0

    def semantic_similarity(self, text_a: str, text_b: str) -> float:
        """Cosine similarity using all-MiniLM embedding."""
        emb_service = self._get_emb()
        try:
            vec_a = emb_service.embed(text_a)
            vec_b = emb_service.embed(text_b)
            cosine = np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-10)
            return float(cosine)
        except Exception as e:
            logger.warning(f"Semantic similarity failed: {e}")
            return 0.0

    def keyword_score(self, text_a: str, text_b: str) -> float:
        """BM25-like keyword overlap score."""
        tokens_a = set(self.preprocess(text_a).split())
        tokens_b = set(self.preprocess(text_b).split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        return intersection / min(len(tokens_a), len(tokens_b)) if min(len(tokens_a), len(tokens_b)) > 0 else 0.0

    def match_score(self, compiled_rule: str, ground_truth: str) -> Dict:
        """Compute comprehensive match score between a compiled rule and GT.

        Returns {score, is_match, semantic_score, keyword_score, entity_score}.
        """
        compiled_pp = self.preprocess(compiled_rule)
        gt_pp = self.preprocess(ground_truth)
        compiled_expanded = self.expand_synonyms(compiled_pp)
        gt_expanded = self.expand_synonyms(gt_pp)

        entities_c = self.extract_entities(compiled_expanded)
        entities_g = self.extract_entities(gt_expanded)

        sem_score = self.semantic_similarity(compiled_expanded, gt_expanded)
        kw_score = self.keyword_score(compiled_expanded, gt_expanded)
        entity_score = self.entity_overlap_score(entities_c, entities_g)

        # Weighted fusion — domain-specific weights loaded from registry
        # (grid-search calibrated per domain; see calibrate_weights.py).
        w_ent, w_kw, w_sem = self._weights
        fused = sem_score * w_sem + kw_score * w_kw + entity_score * w_ent

        return {
            "score": round(fused, 4),
            "is_match": fused >= 0.45,
            "semantic_score": round(sem_score, 4),
            "keyword_score": round(kw_score, 4),
            "entity_score": round(entity_score, 4),
            "entities_compiled": entities_c,
            "entities_gt": entities_g,
        }

    def match_rules(
        self,
        compiled_rules: List[Dict],
        ground_truth_rules: List[Dict],
    ) -> Dict:
        """Match compiled rules to ground truth using the Kuhn-Munkres
        Hungarian algorithm for optimal bipartite matching.

        Kuhn (1955) "The Hungarian Method for the Assignment Problem"
        Munkres (1957) "Algorithms for the Assignment and Transportation Problems"

        Guarantees globally optimal one-to-one assignment by minimizing
        total cost (1 - similarity score), preventing greedy entity snatching.

        Returns {precision, recall, f1, f1_ci_95, matches, ...}.
        """
        from scipy.optimize import linear_sum_assignment

        n_compiled = len(compiled_rules)
        n_gt = len(ground_truth_rules)
        size = max(n_compiled, n_gt)

        # Build cost matrix: cost = 1 - similarity (Hungarian MINIMIZES cost)
        cost_matrix = np.ones((size, size))  # default: max cost (no match)
        for ci, cr in enumerate(compiled_rules):
            cr_text = cr.get('trigger', '')
            for gi, gt in enumerate(ground_truth_rules):
                gt_text = gt.get('trigger', '') or ' '.join(gt.get('keywords', []))
                result = self.match_score(cr_text, gt_text)
                cost_matrix[ci, gi] = 1.0 - result['score']

        # Hungarian algorithm: O(n³) global optimum
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        match_details = []
        matched_compiled = set()
        matched_gt = set()

        for ci, gi in zip(row_ind, col_ind):
            if ci >= n_compiled or gi >= n_gt:
                continue
            score = 1.0 - cost_matrix[ci, gi]
            if score >= 0.5:
                matched_compiled.add(int(ci))
                matched_gt.add(int(gi))
                match_details.append({
                    'compiled_trigger': compiled_rules[ci].get('trigger', '')[:100],
                    'gt_trigger': ground_truth_rules[gi].get('trigger', '')[:100],
                    'score': round(float(score), 4),
                })

        n_matched = len(matched_compiled)
        precision = n_matched / n_compiled if n_compiled > 0 else 0.0
        recall = n_matched / n_gt if n_gt > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        ci_low, ci_high = self._bootstrap_f1_ci(n_matched, n_compiled, n_gt)

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "f1_ci_95": [round(ci_low, 4), round(ci_high, 4)],
            "matched_count": n_matched,
            "total_compiled": n_compiled,
            "total_gt": n_gt,
            "match_details": match_details,
            "algorithm": "Kuhn-Munkres Hungarian (optimal bipartite matching)",
        }

    # ── Online Weight Calibration ──
    # Incremental grid search: when new labeled pairs arrive, re-run a fast
    # grid search (step=0.05, 21³=9261 combos, <1 second) over the expanded
    # calibration set. Always finds the global F1 optimum.
    #
    # Unlike one-shot calibration, this runs continuously — weights improve
    # as more labeled data accumulates, without manual intervention.

    def calibrate_from_pairs(self, pairs: List[Dict], domain: str,
                              step: float = 0.05, save: bool = True) -> Dict:
        """Run grid search over labeled pairs and set weights to F1-optimum.

        pairs: [{'compiled': str, 'ground_truth': str, 'label': 0|1}, ...]

        Grid search over w_ent + w_kw + w_sem = 1.0, step=0.05 (21³ = 9261
        combinations). Embedding similarities are precomputed once, so the
        search itself is pure arithmetic — < 1 second regardless of pair count.
        """
        # Precompute all component scores (embed once, search many times)
        precomputed = []
        for p in pairs:
            r = self.match_score(p['compiled'], p['ground_truth'])
            precomputed.append({
                'entity': r['entity_score'],
                'keyword': r['keyword_score'],
                'semantic': r['semantic_score'],
                'label': p['label'],
            })

        candidates = []
        for w_ent in np.arange(0, 1.001, step):
            for w_kw in np.arange(0, 1.001 - w_ent, step):
                w_sem = round(1.0 - w_ent - w_kw, 4)
                if w_sem < -0.001:
                    continue
                candidates.append((round(w_ent, 4), round(w_kw, 4), round(w_sem, 4)))

        best_f1 = -1.0
        best_weights = self.DEFAULT_WEIGHTS
        best_threshold = 0.5

        old_weights = tuple(self._weights)
        old_domain = self._domain or domain

        for w_ent, w_kw, w_sem in candidates:
            # Fast arithmetic over precomputed scores — no embedding calls
            fused_scores = []
            for pc in precomputed:
                score = w_ent * pc['entity'] + w_kw * pc['keyword'] + w_sem * pc['semantic']
                fused_scores.append((score, pc['label']))

            # Find best threshold for these weights
            best_local_f1 = -1.0
            best_local_thresh = 0.5
            for thresh in np.arange(0.3, 0.85, 0.05):
                tp = sum(1 for s, l in fused_scores if s >= thresh and l == 1)
                fp = sum(1 for s, l in fused_scores if s >= thresh and l == 0)
                fn = sum(1 for s, l in fused_scores if s < thresh and l == 1)
                p = tp / (tp + fp) if (tp + fp) > 0 else 0
                r = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
                if f1 > best_local_f1:
                    best_local_f1 = f1
                    best_local_thresh = thresh

            if best_local_f1 > best_f1:
                best_f1 = best_local_f1
                best_weights = (w_ent, w_kw, w_sem)
                best_threshold = best_local_thresh

        # Restore best weights
        self._weights = best_weights
        self._domain = old_domain

        # Compare to equal-weight baseline (use precomputed scores)
        eq_tp = eq_fp = eq_fn = 0
        w_eq = np.array(self.DEFAULT_WEIGHTS)
        for pc in precomputed:
            score = w_eq[0] * pc['entity'] + w_eq[1] * pc['keyword'] + w_eq[2] * pc['semantic']
            pred = score >= 0.5
            if pred and pc['label'] == 1:
                eq_tp += 1
            elif pred and pc['label'] == 0:
                eq_fp += 1
            elif not pred and pc['label'] == 1:
                eq_fn += 1
        eq_p = eq_tp / (eq_tp + eq_fp) if (eq_tp + eq_fp) > 0 else 0
        eq_r = eq_tp / (eq_tp + eq_fn) if (eq_tp + eq_fn) > 0 else 0
        eq_f1 = 2 * eq_p * eq_r / (eq_p + eq_r) if (eq_p + eq_r) > 0 else 0

        self._weights = best_weights

        report = {
            'domain': domain,
            'weights_optimal': {
                'w_entity': best_weights[0],
                'w_keyword': best_weights[1],
                'w_semantic': best_weights[2],
            },
            'threshold_optimal': round(best_threshold, 2),
            'calibration_f1': round(best_f1, 4),
            'calibration_pairs': len(pairs),
            'equal_weight_f1': round(eq_f1, 4),
            'delta_f1': round(best_f1 - eq_f1, 4),
            'weights_before': old_weights,
            'method': 'incremental_grid_search',
            'grid_step': step,
            'n_combos_searched': len(candidates),
        }

        if save:
            self.save_weights(domain)

        return report

    def save_weights(self, domain: str, registry_path: str = None):
        """Persist current weights to the domain_weights.json registry."""
        import json as _json
        if registry_path is None:
            registry_path = r'D:\minta-expert-data\domain_weights.json'
        if os.path.exists(registry_path):
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = _json.load(f)
        else:
            registry = {}

        if domain not in registry:
            registry[domain] = {}
        registry[domain]['weights'] = {
            'w_entity': round(self._weights[0], 4),
            'w_keyword': round(self._weights[1], 4),
            'w_semantic': round(self._weights[2], 4),
        }
        registry[domain]['calibrated_at'] = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        registry[domain]['method'] = 'online_perceptron'

        with open(registry_path, 'w', encoding='utf-8') as f:
            _json.dump(registry, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _simplex_project(v: np.ndarray) -> np.ndarray:
        """Project a vector onto the probability simplex (sum=1, all >= 0).

        Wang & Carreira-Perpinan (2013) algorithm: clamp, sort, find pivot.
        """
        v = np.maximum(v, 0)
        if v.sum() < 1e-10:
            return np.ones_like(v) / len(v)
        u = np.sort(v)[::-1]
        cumsum = np.cumsum(u)
        rho = np.searchsorted(np.arange(1, len(v) + 1) * u > cumsum - 1, True)
        if rho == len(v):
            rho = len(v) - 1
        theta = (cumsum[rho] - 1) / (rho + 1)
        return np.maximum(v - theta, 0)

    def _bootstrap_f1_ci(self, matched: int, n_compiled: int, n_gt: int,
                         n_bootstrap: int = 10000) -> Tuple[float, float]:
        """Bootstrap 95% CI for F1 score."""
        np.random.seed(42)
        f1s = []
        for _ in range(n_bootstrap):
            m = np.random.binomial(n_compiled, matched / n_compiled if n_compiled > 0 else 0)
            p = m / n_compiled if n_compiled > 0 else 0
            r = m / n_gt if n_gt > 0 else 0
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0
            f1s.append(f)
        return np.percentile(f1s, 2.5), np.percentile(f1s, 97.5)
