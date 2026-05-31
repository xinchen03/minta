"""Evaluation metrics for Minta Expert experiments.

Four verification layers:
1. Compilation correctness — does the compiler correctly extract rules from CPG?
2. Execution correctness — do compiled rules match original CPG performance?
3. Rule Promotion ablation — does adaptive confidence improve accuracy?
4. Behavior Abstraction ablation — does abstraction improve recall on synonyms?
"""
from __future__ import annotations
from typing import List, Dict, Tuple
from collections import defaultdict


def compilation_accuracy(
    compiled_rules: List[Dict],
    ground_truth_rules: List[Dict],
    field_keys: Tuple[str, ...] = ("trigger", "action"),
) -> Dict:
    """Compute compilation correctness metrics.

    Args:
        compiled_rules: Rules extracted by domain_compiler
        ground_truth_rules: Ground truth rules from CPG reference
        field_keys: Fields to compare (trigger, action)

    Returns:
        {precision, recall, f1, exact_matches, total_gt, total_compiled}
    """
    matched = 0
    unmatched_gt = list(ground_truth_rules)
    unmatched_comp = list(compiled_rules)

    matches = []
    for comp in compiled_rules[:]:
        for gt in unmatched_gt[:]:
            if all(_field_match(comp.get(f, ""), gt.get(f, ""))
                   for f in field_keys):
                matches.append((comp, gt))
                unmatched_comp = [c for c in unmatched_comp if c != comp]
                unmatched_gt = [g for g in unmatched_gt if g != gt]
                matched += 1
                break

    total_gt = len(ground_truth_rules)
    total_comp = len(compiled_rules)

    precision = matched / total_comp if total_comp > 0 else 0.0
    recall = matched / total_gt if total_gt > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Check for hallucinated rules (compiled but not in ground truth)
    hallucinated = len(unmatched_comp)

    # Check for missed rules (in ground truth but not compiled)
    missed = len(unmatched_gt)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "exact_matches": matched,
        "hallucinated_rules": hallucinated,
        "missed_rules": missed,
        "total_gt": total_gt,
        "total_compiled": total_comp,
    }


def _field_match(a: str, b: str, threshold: float = 0.6) -> bool:
    """Check if two text fields match (fuzzy)."""
    from difflib import SequenceMatcher
    a_clean = a.lower().strip()
    b_clean = b.lower().strip()
    if a_clean == b_clean:
        return True
    if a_clean in b_clean or b_clean in a_clean:
        return True
    return SequenceMatcher(None, a_clean, b_clean).ratio() >= threshold


def execution_correctness(
    predictions: List[bool],
    ground_truth: List[bool],
) -> Dict:
    """Compute sensitivity, specificity, and reduction metrics.

    Args:
        predictions: System's decision (True = recommend imaging)
        ground_truth: Actual outcome (True = fracture present)

    Returns:
        {sensitivity, specificity, ppv, npv, accuracy, n}
    """
    n = len(predictions)
    if n == 0:
        return {"sensitivity": 0, "specificity": 0, "accuracy": 0, "n": 0}

    tp = sum(1 for p, g in zip(predictions, ground_truth) if p and g)
    tn = sum(1 for p, g in zip(predictions, ground_truth) if not p and not g)
    fp = sum(1 for p, g in zip(predictions, ground_truth) if p and not g)
    fn = sum(1 for p, g in zip(predictions, ground_truth) if not p and g)

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    npv = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    accuracy = (tp + tn) / n

    # Imaging reduction rate (compared to "image everyone" baseline)
    imaging_rate = (tp + fp) / n
    reduction = 1.0 - imaging_rate

    return {
        "sensitivity": round(sensitivity, 4),
        "specificity": round(specificity, 4),
        "ppv": round(ppv, 4),
        "npv": round(npv, 4),
        "accuracy": round(accuracy, 4),
        "imaging_rate": round(imaging_rate, 4),
        "imaging_reduction": round(reduction, 4),
        "n": n,
    }


def ablation_metrics(
    results_on: Dict,
    results_off: Dict,
) -> Dict:
    """Compute ablation comparison metrics.

    Args:
        results_on: Metrics with the module enabled
        results_off: Metrics with the module disabled

    Returns:
        {metric_deltas, improvement_pct}
    """
    deltas = {}
    for key in results_on:
        if key in results_off and isinstance(results_on[key], (int, float)):
            deltas[key] = round(results_on[key] - results_off[key], 4)

    return {
        "on": results_on,
        "off": results_off,
        "deltas": deltas,
    }


def recall_at_k(
    retrieved_ids: List[List[str]],
    relevant_ids: List[List[str]],
    ks: List[int] = [1, 3, 5, 10],
) -> Dict[int, float]:
    """Compute Recall@K for retrieval evaluation."""
    results = {}
    for k in ks:
        recalls = []
        for ret, rel in zip(retrieved_ids, relevant_ids):
            if not rel:
                continue
            top_k = set(ret[:k])
            relevant = set(rel)
            recall = len(top_k & relevant) / len(relevant)
            recalls.append(recall)
        results[k] = round(sum(recalls) / len(recalls), 4) if recalls else 0.0
    return results
