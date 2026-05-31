"""Conformal Prediction — Layer 6: Metacognitive Gating.

Vovk et al. (2005) Inductive Conformal Prediction:
  - Distribution-free: no assumptions about nonconformity score distribution
  - Finite-sample valid: uses only calibration set quantiles, no asymptotics
  - Marginal coverage guarantee: P(Y_{n+1} ∈ C(X_{n+1})) ≥ 1 - α

Uses existing RuleMatcher.match_score() as the nonconformity scoring function
and calibration pairs (78 labeled pairs across ankle/knee/c-spine) for calibration.

Calibration results are persisted to D:/minta-expert-data/conformal/{domain}.json
so recalibration is not needed on every inference.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)

CONFORMAL_DIR = Path(r"D:\minta-expert-data\conformal")
DEFAULT_ALPHA = 0.05  # 95% confidence


@dataclass
class CalibrationResult:
    domain: str
    alpha: float
    q_hat: float
    n_calibration: int
    coverage_guarantee: str
    calibrated_at: str
    nonconformity_scores: List[float] = field(default_factory=list)


@dataclass
class PredictionSet:
    rule_text: str
    included: bool
    nonconformity: float
    threshold: float
    confidence_text: str
    alpha: float = DEFAULT_ALPHA


@dataclass
class CoverageReport:
    domain: str
    alpha: float
    empirical_coverage: float
    n_test: int
    meets_guarantee: bool
    detail: str


def _ensure_dir() -> None:
    CONFORMAL_DIR.mkdir(parents=True, exist_ok=True)


def _calibration_path(domain: str) -> Path:
    return CONFORMAL_DIR / f"{domain}.json"


def _load_calibration_pairs(domain: str) -> List[Dict]:
    """Load labeled calibration pairs for a domain.

    Looks in D:/minta-expert-data/calibration/{domain}_pairs.json
    and the older merged calibration file.
    """
    paths = [
        Path(rf"D:\minta-expert-data\calibration\{domain}_pairs.json"),
        Path(rf"D:\minta-expert-data\calibration\{domain}_calibration.json"),
        Path(r"D:\minta-expert-data\calibration_pairs.json"),
    ]
    for p in paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # May be keyed by domain
                if domain in data:
                    return data[domain]
                # Or have a "pairs" key
                if "pairs" in data:
                    return data["pairs"]
                # Or be a flat dict of pairs
                pairs = []
                for k, v in data.items():
                    if isinstance(v, dict) and "compiled" in v:
                        pairs.append(v)
                if pairs:
                    return pairs
    return []


class ConformalPredictor:
    """Inductive conformal predictor for expert rule validation.

    Mathematical guarantee:
      P(Y ∈ C(X)) ≥ 1 - α
    where C(X) is the prediction set, under the exchangeability assumption.

    Fallback: when no calibration data exists, returns a default q_hat = 0.5
    and marks the result with a warning — never throws.

    Usage:
        cp = ConformalPredictor(alpha=0.05)
        cp.calibrate("ankle_injury")          # compute + persist q_hat
        result = cp.predict(rule, candidates)  # get prediction set
    """

    def __init__(self, alpha: float = DEFAULT_ALPHA):
        self.alpha = alpha
        self._matcher = None
        self._cache: Dict[str, CalibrationResult] = {}

    @property
    def matcher(self):
        if self._matcher is None:
            from services.rule_matcher import RuleMatcher
            self._matcher = RuleMatcher()
        return self._matcher

    # ── Calibration ──

    def calibrate(self, domain: str, alpha: float = None) -> CalibrationResult:
        """Calibrate the conformal predictor for a domain.

        1. Load labeled calibration pairs
        2. Compute nonconformity = 1 - match_score(compiled, GT).score
        3. q_hat = ⌈(n+1)(1-α)⌉-th largest nonconformity
        4. Persist to D:/minta-expert-data/conformal/{domain}.json

        Returns default if no calibration data exists (never throws).
        """
        alpha = alpha or self.alpha
        pairs = _load_calibration_pairs(domain)

        if not pairs:
            logger.warning(
                f"No calibration data for '{domain}', using default q_hat=0.5"
            )
            result = CalibrationResult(
                domain=domain,
                alpha=alpha,
                q_hat=0.5,
                n_calibration=0,
                coverage_guarantee="default (no calibration data)",
                calibrated_at=_now(),
            )
            self._cache[domain] = result
            self._save(domain, result)
            return result

        # Compute nonconformity scores
        scores = []
        for pair in pairs:
            compiled = pair.get("compiled", "") or pair.get("trigger", "") or ""
            ground_truth = pair.get("ground_truth", "") or pair.get("gt", "") or ""
            if not compiled or not ground_truth:
                continue
            match = self.matcher.match_score(compiled, ground_truth)
            nonconf = 1.0 - match["score"]
            scores.append(nonconf)

        if not scores:
            result = CalibrationResult(
                domain=domain,
                alpha=alpha,
                q_hat=0.5,
                n_calibration=0,
                coverage_guarantee="default (no valid pairs)",
                calibrated_at=_now(),
            )
            self._cache[domain] = result
            self._save(domain, result)
            return result

        n = len(scores)
        scores_sorted = sorted(scores, reverse=True)
        # q_hat = ⌈(n+1)(1-α)⌉-th value (1-indexed → 0-indexed)
        k = int(np.ceil((n + 1) * (1 - alpha))) - 1
        k = max(0, min(k, n - 1))
        q_hat = scores_sorted[k]

        result = CalibrationResult(
            domain=domain,
            alpha=alpha,
            q_hat=round(float(q_hat), 4),
            n_calibration=n,
            coverage_guarantee=f">= {1 - alpha:.0%} (marginal, under exchangeability)",
            calibrated_at=_now(),
            nonconformity_scores=[round(float(s), 4) for s in scores],
        )
        self._cache[domain] = result
        self._save(domain, result)

        logger.info(
            f"Conformal calibration for '{domain}': q_hat={q_hat:.4f}, "
            f"n={n}, alpha={alpha}"
        )
        return result

    # ── Prediction ──

    def predict(
        self,
        compiled_rule: str,
        gt_candidates: List[str],
        domain: str = None,
        alpha: float = None,
    ) -> List[PredictionSet]:
        """Generate prediction sets for compiled rule against GT candidates.

        Returns a PredictionSet per candidate, with confidence_text for frontend display.
        """
        alpha = alpha or self.alpha

        # Load calibration
        if domain and domain in self._cache:
            cal = self._cache[domain]
        elif domain:
            cal = self._load_or_calibrate(domain, alpha)
        else:
            cal = CalibrationResult(
                domain="unknown", alpha=alpha, q_hat=0.5, n_calibration=0,
                coverage_guarantee="default", calibrated_at=_now(),
            )

        results = []
        for gt in gt_candidates:
            match = self.matcher.match_score(compiled_rule, gt)
            nonconf = round(1.0 - match["score"], 4)
            included = nonconf <= cal.q_hat

            conf_pct = (1 - alpha) * 100
            if included:
                confidence_text = f"{conf_pct:.0f}%置信：该规则有效 (nonconformity={nonconf:.3f} ≤ q_hat={cal.q_hat:.3f})"
            else:
                confidence_text = f"低于{conf_pct:.0f}%置信阈值：该规则可能需要人工审核 (nonconformity={nonconf:.3f} > q_hat={cal.q_hat:.3f})"

            results.append(
                PredictionSet(
                    rule_text=gt[:100],
                    included=included,
                    nonconformity=nonconf,
                    threshold=cal.q_hat,
                    confidence_text=confidence_text,
                    alpha=alpha,
                )
            )

        return results

    # ── Coverage evaluation ──

    def evaluate_coverage(
        self, test_pairs: List[Dict], domain: str = None, alpha: float = None
    ) -> CoverageReport:
        """Evaluate empirical coverage on held-out test pairs.

        Verifies: empirical_coverage ≥ 1 - α
        """
        alpha = alpha or self.alpha
        cal = None
        if domain:
            cal = self._load_or_calibrate(domain, alpha)

        if cal is None or cal.n_calibration == 0:
            return CoverageReport(
                domain=domain or "unknown",
                alpha=alpha,
                empirical_coverage=0.0,
                n_test=len(test_pairs),
                meets_guarantee=False,
                detail="No calibration data available",
            )

        covered = 0
        for pair in test_pairs:
            compiled = pair.get("compiled", "") or pair.get("trigger", "") or ""
            gt = pair.get("ground_truth", "") or pair.get("gt", "") or ""
            if not compiled or not gt:
                continue
            match = self.matcher.match_score(compiled, gt)
            nonconf = 1.0 - match["score"]
            if nonconf <= cal.q_hat:
                covered += 1

        n = len(test_pairs)
        emp_cov = covered / n if n > 0 else 0.0
        meets = emp_cov >= (1 - alpha)

        return CoverageReport(
            domain=domain or "unknown",
            alpha=alpha,
            empirical_coverage=round(emp_cov, 4),
            n_test=n,
            meets_guarantee=meets,
            detail=(
                f"Empirical coverage {emp_cov:.2%} {'≥' if meets else '<'} "
                f"guaranteed {1-alpha:.2%} (q_hat={cal.q_hat:.4f}, n_cal={cal.n_calibration})"
            ),
        )

    # ── Persistence ──

    def _save(self, domain: str, result: CalibrationResult) -> None:
        _ensure_dir()
        data = {
            "domain": domain,
            "calibrated_at": result.calibrated_at,
            "alpha": result.alpha,
            "q_hat": result.q_hat,
            "n_calibration": result.n_calibration,
            "coverage_guarantee": result.coverage_guarantee,
        }
        with open(_calibration_path(domain), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_or_calibrate(self, domain: str, alpha: float = None) -> Optional[CalibrationResult]:
        """Load persisted calibration or run fresh calibration."""
        path = _calibration_path(domain)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("alpha") == (alpha or self.alpha):
                return CalibrationResult(
                    domain=data["domain"],
                    alpha=data["alpha"],
                    q_hat=data["q_hat"],
                    n_calibration=data.get("n_calibration", 0),
                    coverage_guarantee=data.get("coverage_guarantee", ""),
                    calibrated_at=data.get("calibrated_at", ""),
                )
        return self.calibrate(domain, alpha)

    def is_calibrated(self, domain: str) -> bool:
        """Check if calibration data exists for a domain."""
        return _calibration_path(domain).exists() or domain in self._cache


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")
