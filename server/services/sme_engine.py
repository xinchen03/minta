"""SME Structure-Mapping Engine — Layer 4: Analogical Reasoning.

Based on Gentner (1983) Structure-Mapping Theory:
  MAC stage: Many Are Called — coarse filter by shared cognitive operations
  FAC stage: Few Are Chosen — fine-grained structural alignment

Graph knowledge network built on networkx.DiGraph:
  Nodes: domain experts, cognitive operations, production rules
  Edges: shares_operation, consults, contradicts, corroborates

Meta-reasoning = weighted path traversal on the knowledge graph.
Every step traceable to a specific shared cognitive operation.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import networkx as nx

logger = logging.getLogger(__name__)

EDGE_TYPES = ("shares_operation", "consults", "contradicts", "corroborates")

DEFAULT_CONFIG_PATH = Path(r"D:\minta-expert-data\sme_config.json")

DEFAULT_CONFIG = {
    "min_shared_ops": 2,
    "similarity_threshold": 0.6,
    "weights": {"w_seq": 0.5, "w_path": 0.3, "w_conf": 0.2},
    "transfer_safety": {
        "require_same_anatomical_site": True,
        "require_same_clinical_task": True,
    },
}


def _load_config(path: Optional[str] = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_CONFIG)


@dataclass
class DomainSignature:
    domain: str
    operations: List[str] = field(default_factory=list)
    decision_paths: List[str] = field(default_factory=list)
    confidence_distribution: Dict[str, float] = field(default_factory=dict)
    rule_count: int = 0


@dataclass
class AnalogyResult:
    source_domain: str
    target_domain: str
    structural_similarity: float
    shared_operations: List[str]
    edge_type: str = "shares_operation"
    transfer_suggestions: List[str] = field(default_factory=list)


@dataclass
class RuleTransfer:
    source_trigger: str
    source_action: str
    target_domain: str
    rationale: str
    confidence: float


class SMEEngine:
    """Structure-Mapping Engine with networkx.DiGraph knowledge network.

    MAC -> FAC pipeline for cross-domain analogy discovery.
    Graph queries for meta-reasoning: neighbors, shortest paths,
    operation-based domain networks, weighted counter-example routing.

    Usage:
        sme = SMEEngine()
        sme.build_graph(db, user_id)                         # populate graph from DB
        analogies = sme.find_analogies("ankle", ["knee"])    # discover links
        neighbors = sme.graph_neighbors("ankle")             # graph query
        path = sme.shortest_path("ankle", "cervical_spine")  # meta-reasoning
        transfers = sme.suggest_rule_transfer(analogy, db)   # real rule migration
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config = _load_config(config_path)
        self.graph = nx.DiGraph()
        self._ba = None

    @property
    def ba(self):
        if self._ba is None:
            from services.behavior_abstraction import BehaviorAbstraction
            self._ba = BehaviorAbstraction()
        return self._ba

    # ── Graph construction ──

    def build_graph(self, db, user_id: int) -> int:
        """Populate the DiGraph from all registered domain experts and their rules.

        Nodes: domain nodes + operation nodes
        Edges: domain --[shares_operation]--> domain (bidirectional, weighted)
               domain --[has_operation]--> operation

        Returns number of nodes in the graph.
        """
        from services.meta_expert import get_meta_expert
        from services.production_store import list_rules as list_expert_rules

        self.graph.clear()
        meta = get_meta_expert(db)
        experts = meta.list_experts()

        # Add domain nodes
        for expert in experts:
            domain = expert.get("domain", "")
            if not domain:
                continue
            self.graph.add_node(
                domain,
                type="domain",
                title=expert.get("title", domain),
                agent_type=expert.get("agent_type", "contributory"),
                rule_count=expert.get("rule_count", 0),
            )

        # Extract signatures, add operation nodes, and build edges
        domain_signatures: Dict[str, DomainSignature] = {}
        for expert in experts:
            domain = expert.get("domain", "")
            if not domain:
                continue
            rules = list_expert_rules(db, user_id, domain=domain, limit=100)
            sig = self.extract_domain_signature(domain, rules)
            if sig is None:
                continue
            domain_signatures[domain] = sig

            # Add operation nodes and domain->operation edges
            for op in sig.operations:
                if not self.graph.has_node(op):
                    self.graph.add_node(op, type="operation")
                if self.graph.has_edge(domain, op):
                    self.graph[domain][op]["weight"] += 1
                else:
                    self.graph.add_edge(domain, op, type="has_operation", weight=1)

        # Discover cross-domain links: MAC stage across all domain pairs
        domains = list(domain_signatures.keys())
        for i, d1 in enumerate(domains):
            for d2 in domains[i + 1:]:
                sig1 = domain_signatures[d1]
                sig2 = domain_signatures[d2]
                if not self.mac_stage(sig1, sig2):
                    continue
                sim = self.fac_stage(sig1, sig2)
                threshold = self.config.get("similarity_threshold", 0.6)
                if sim < threshold:
                    continue
                shared = sorted(set(sig1.operations) & set(sig2.operations))
                # Bidirectional weighted edges
                self.graph.add_edge(d1, d2, type="shares_operation",
                                    weight=sim, shared_ops=shared)
                self.graph.add_edge(d2, d1, type="shares_operation",
                                    weight=sim, shared_ops=shared)
                logger.info(f"Graph edge: {d1} <-> {d2} (sim={sim:.3f}, ops={shared[:4]})")

        return self.graph.number_of_nodes()

    # ── Graph queries (meta-reasoning) ──

    def graph_neighbors(
        self, domain: str, edge_type: str = None, min_weight: float = 0.0
    ) -> List[Dict]:
        """Get all neighbors of a domain node, optionally filtered by edge type."""
        if domain not in self.graph:
            return []
        results = []
        for neighbor in self.graph.neighbors(domain):
            edge = self.graph[domain][neighbor]
            if edge_type and edge.get("type") != edge_type:
                continue
            if edge.get("weight", 0) < min_weight:
                continue
            results.append({
                "domain": neighbor,
                "edge_type": edge.get("type"),
                "weight": edge.get("weight"),
                "shared_ops": edge.get("shared_ops", []),
            })
        return sorted(results, key=lambda r: r["weight"], reverse=True)

    def shortest_path(
        self, source: str, target: str, edge_type: str = None
    ) -> Optional[List[str]]:
        """Find shortest path between two domains in the knowledge graph.

        This IS meta-reasoning: "how are ankle and cervical-spine connected?"
        The path reveals the chain of shared cognitive operations.
        """
        if source not in self.graph or target not in self.graph:
            return None
        try:
            if edge_type:
                subgraph = nx.DiGraph()
                for u, v, data in self.graph.edges(data=True):
                    if data.get("type") == edge_type:
                        subgraph.add_edge(u, v, **data)
                return nx.shortest_path(subgraph, source=source, target=target)
            return nx.shortest_path(self.graph, source=source, target=target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def query_by_operation(self, operation: str) -> List[str]:
        """Find all domains that have a given cognitive operation.

        Graph equivalent: incoming neighbors of the operation node.
        """
        if operation not in self.graph:
            return []
        return list(self.graph.predecessors(operation))

    def get_operation_network(self, operation: str) -> List[Dict]:
        """Get all domain pairs that share a given operation."""
        domains = self.query_by_operation(operation)
        pairs = []
        for i, d1 in enumerate(domains):
            for d2 in domains[i + 1:]:
                edge = self.graph.get_edge_data(d1, d2) or self.graph.get_edge_data(d2, d1)
                pairs.append({
                    "domain_a": d1, "domain_b": d2,
                    "shared_operation": operation,
                    "similarity": edge.get("weight", 0) if edge else 0,
                })
        return pairs

    def get_counter_example_routes(self, source_domain: str) -> List[Dict]:
        """Find all domains reachable from source where counter-examples can propagate.

        Traverses shares_operation edges up to depth 2.
        """
        if source_domain not in self.graph:
            return []
        routes = []
        for neighbor in self.graph.neighbors(source_domain):
            edge = self.graph[source_domain][neighbor]
            if edge.get("type") != "shares_operation":
                continue
            routes.append({
                "target": neighbor,
                "distance": 1,
                "shared_ops": edge.get("shared_ops", []),
                "confidence": edge.get("weight", 0),
            })
            # Depth 2: neighbor of neighbor
            for n2 in self.graph.neighbors(neighbor):
                if n2 == source_domain or n2 in [r["target"] for r in routes]:
                    continue
                e2 = self.graph[neighbor][n2]
                if e2.get("type") != "shares_operation":
                    continue
                routes.append({
                    "target": n2,
                    "distance": 2,
                    "shared_ops": e2.get("shared_ops", []),
                    "confidence": edge.get("weight", 0) * e2.get("weight", 0),
                })
        return sorted(routes, key=lambda r: r["confidence"], reverse=True)

    # ── Signature extraction ──

    def extract_domain_signature(
        self, domain: str, rules: List
    ) -> Optional[DomainSignature]:
        """Extract cognitive operation signature from a domain's rule set.

        Returns None if rules list is empty (null protection).
        """
        if not rules:
            return None

        all_ops = []
        decision_paths = []
        conf_dist = {}

        for rule in rules:
            trigger = getattr(rule, "trigger", "") or getattr(rule, "summary", "") or ""
            action = getattr(rule, "action", "") or getattr(rule, "body", "") or ""
            conf = getattr(rule, "confidence", 0.5)
            if isinstance(conf, (int, float)) and conf > 1:
                conf = conf / 5.0

            trigger_ops = self.ba.abstract_sequence([trigger])
            action_ops = self.ba.abstract_sequence([action])
            all_ops.extend(trigger_ops)
            all_ops.extend(action_ops)

            path = f"{trigger[:60]}->{action[:40]}"
            if path not in decision_paths:
                decision_paths.append(path)

            stage = getattr(rule, "stage", None)
            stage_key = str(stage) if stage else "unknown"
            conf_dist[stage_key] = conf_dist.get(stage_key, 0.0) + conf

        seen = set()
        unique_ops = []
        for op in all_ops:
            if op and op not in seen:
                seen.add(op)
                unique_ops.append(op)

        return DomainSignature(
            domain=domain,
            operations=unique_ops,
            decision_paths=decision_paths,
            confidence_distribution=conf_dist,
            rule_count=len(rules),
        )

    # ── MAC stage ──

    def mac_stage(self, source: DomainSignature, target: DomainSignature) -> bool:
        if source is None or target is None:
            return False
        shared = set(source.operations) & set(target.operations)
        return len(shared) >= self.config.get("min_shared_ops", 2)

    def _shared_operations(
        self, source: DomainSignature, target: DomainSignature
    ) -> List[str]:
        if source is None or target is None:
            return []
        return sorted(set(source.operations) & set(target.operations))

    # ── FAC stage ──

    def fac_stage(self, source: DomainSignature, target: DomainSignature) -> float:
        if source is None or target is None:
            return 0.0

        w = self.config.get("weights", DEFAULT_CONFIG["weights"])

        seq_sim = self.ba.structural_similarity(source.operations, target.operations)

        path_sim = 0.0
        if source.decision_paths and target.decision_paths:
            src_paths = " | ".join(source.decision_paths[:10])
            tgt_paths = " | ".join(target.decision_paths[:10])
            path_sim = SequenceMatcher(None, src_paths, tgt_paths).ratio()

        conf_sim = 0.0
        all_stages = set(source.confidence_distribution.keys()) | set(
            target.confidence_distribution.keys()
        )
        if all_stages:
            src_vec = [source.confidence_distribution.get(s, 0.0) for s in all_stages]
            tgt_vec = [target.confidence_distribution.get(s, 0.0) for s in all_stages]
            dot = sum(a * b for a, b in zip(src_vec, tgt_vec))
            norm_src = sum(x * x for x in src_vec) ** 0.5
            norm_tgt = sum(x * x for x in tgt_vec) ** 0.5
            if norm_src > 0 and norm_tgt > 0:
                conf_sim = dot / (norm_src * norm_tgt)

        return w["w_seq"] * seq_sim + w["w_path"] * path_sim + w["w_conf"] * conf_sim

    # ── Main entry point ──

    def find_analogies(
        self,
        source_domain: str,
        target_domains: List[str],
        db=None,
        user_id: int = None,
    ) -> List[AnalogyResult]:
        """Run MAC->FAC pipeline and auto-link via MetaExpert + graph edges."""
        from services.production_store import list_rules as list_expert_rules

        if not target_domains:
            return []

        src_rules = list_expert_rules(db, user_id, domain=source_domain, limit=100) if db else []
        src_sig = self.extract_domain_signature(source_domain, src_rules)
        if src_sig is None:
            return []

        results = []
        for target_domain in target_domains:
            if target_domain == source_domain:
                continue
            tgt_rules = list_expert_rules(db, user_id, domain=target_domain, limit=100) if db else []
            tgt_sig = self.extract_domain_signature(target_domain, tgt_rules)
            if tgt_sig is None:
                continue
            if not self.mac_stage(src_sig, tgt_sig):
                continue

            sim = self.fac_stage(src_sig, tgt_sig)
            if sim < self.config.get("similarity_threshold", 0.6):
                continue

            shared = self._shared_operations(src_sig, tgt_sig)
            result = AnalogyResult(
                source_domain=source_domain,
                target_domain=target_domain,
                structural_similarity=round(sim, 4),
                shared_operations=shared,
            )

            # Graph: add bidirectional edges
            self.graph.add_edge(source_domain, target_domain,
                                type="shares_operation", weight=sim, shared_ops=shared)
            self.graph.add_edge(target_domain, source_domain,
                                type="shares_operation", weight=sim, shared_ops=shared)

            # Meta link + counter-example propagation
            if db and user_id is not None:
                try:
                    from services.meta_expert import get_meta_expert
                    meta = get_meta_expert(db)
                    meta.link_domains_by_operation(
                        source_domain, target_domain,
                        shared_operations=shared, similarity=sim,
                    )
                    meta.propagate_counter_example(
                        source_domain, target_domain,
                        shared_operations=shared,
                    )
                    result.transfer_suggestions = [
                        f"反例从 '{source_domain}' 传播到 '{target_domain}' "
                        f"via {', '.join(shared[:5])}"
                    ]
                except Exception as e:
                    logger.warning(f"SME auto-link failed: {e}")

            results.append(result)

        return results

    # ── Rule transfer: real rules, not heuristic labels ──

    def suggest_rule_transfer(
        self, analogy: AnalogyResult, db=None, user_id: int = None
    ) -> List[RuleTransfer]:
        """Suggest DECISION PATTERN transfers, not literal trigger copies.

        Scientific premise (Gentner 1983): structure-mapping transfers the
        relational STRUCTURE, not the surface attributes. In clinical terms:
        - Shared operation "PHYSICAL_EXAM_PALPATION" means: "IF landmark tenderness THEN X"
        - The specific landmark ("lateral malleolus" vs "head of fibula") is SURFACE, not structure
        - Sharing the same clinical task (e.g. "triage imaging decision") enables transfer

        Safety:
        - require_same_clinical_task: only transfer if domains share >= 2 operations
          (indicating same clinical reasoning pattern)
        - NO anatomical site check: the pattern "palpation → imaging" is valid across body parts
        - Transfer returns the ABSTRACT PATTERN, not the literal trigger text
        """
        safety = self.config.get("transfer_safety", {})
        require_task = safety.get("require_same_clinical_task", True)

        # Clinical task gate: need >= 2 shared ops to indicate same reasoning pattern
        if require_task and len(analogy.shared_operations) < 2:
            return []

        if not db or user_id is None:
            return []

        from services.production_store import list_rules as list_expert_rules
        src_rules = list_expert_rules(db, user_id, domain=analogy.source_domain, limit=50)
        if not src_rules:
            return []

        shared_ops = set(analogy.shared_operations)
        transfers = []

        for rule in src_rules:
            trigger = getattr(rule, "trigger", "") or getattr(rule, "summary", "") or ""
            action = getattr(rule, "action", "") or getattr(rule, "body", "") or ""
            conf = getattr(rule, "confidence", 0.5)
            if isinstance(conf, (int, float)) and conf > 1:
                conf = conf / 5.0

            trigger_ops = set(self.ba.abstract_sequence([trigger]))
            action_ops = set(self.ba.abstract_sequence([action]))
            rule_ops = trigger_ops | action_ops

            if rule_ops & shared_ops:
                # Build abstract pattern: operations involved, not literal text
                active_ops = sorted(rule_ops & shared_ops)
                transfer = RuleTransfer(
                    source_trigger=trigger[:120],
                    source_action=action[:80],
                    target_domain=analogy.target_domain,
                    rationale=(
                        f"Pattern: {', '.join(active_ops)}. "
                        f"This cognitive operation sequence is shared between "
                        f"{analogy.source_domain} and {analogy.target_domain}"
                    ),
                    confidence=round(conf * analogy.structural_similarity, 4),
                )
                transfers.append(transfer)

        # Sort by confidence, return top 10
        transfers.sort(key=lambda t: t.confidence, reverse=True)
        return transfers[:10]

    def auto_transfer(
        self, source_domain: str, db, user_id: int
    ) -> Dict:
        """Full auto-transfer pipeline: find analogies + suggest transfers.

        Returns summary suitable for conversation display.
        """
        neighbors = self.graph_neighbors(source_domain, edge_type="shares_operation")
        if not neighbors:
            return {"analogies": 0, "transfers": 0, "detail": []}

        detail = []
        total_transfers = 0
        for n in neighbors:
            analogy = AnalogyResult(
                source_domain=source_domain,
                target_domain=n["domain"],
                structural_similarity=n["weight"],
                shared_operations=n["shared_ops"],
            )
            transfers = self.suggest_rule_transfer(analogy, db, user_id)
            total_transfers += len(transfers)
            detail.append({
                "target": n["domain"],
                "similarity": n["weight"],
                "shared_ops": n["shared_ops"],
                "transfer_count": len(transfers),
                "sample_transfers": [
                    {"trigger": t.source_trigger[:80], "rationale": t.rationale[:100]}
                    for t in transfers[:3]
                ],
            })

        return {
            "source": source_domain,
            "analogies": len(neighbors),
            "transfers": total_transfers,
            "detail": detail,
        }
