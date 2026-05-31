"""Decision Graph Miner — extract decision structures from conversation traces.

Unlike domain_compiler (which works from CPG text), this module mines
decision patterns from expert-user conversation logs: what questions were
asked, in what order, leading to what conclusions.

Algorithm:
1. Cluster sessions by domain/task type
2. Extract question→answer→decision triples
3. Align similar decision paths across sessions
4. Merge into consolidated DecisionGraph
5. Feed into RulePromotionPipeline for stage classification
"""
from __future__ import annotations
import re
import uuid
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from schemas.decision_graph import DecisionGraph, DecisionNode, PriorityPath, DecisionTrace

logger = logging.getLogger(__name__)

# Minimum sessions needed to start mining
MIN_SESSIONS = 3
# Minimum path frequency to include in graph
MIN_PATH_FREQ = 2
# Similarity threshold for merging paths
MERGE_THRESHOLD = 0.7


class DecisionGraphMiner:
    """Mine decision graphs from session-level decision traces."""

    def __init__(self):
        pass

    def mine_from_traces(
        self,
        traces: List[DecisionTrace],
        domain: str = "",
        min_sessions: int = MIN_SESSIONS,
    ) -> Optional[DecisionGraph]:
        """Mine a DecisionGraph from a list of decision traces.

        Args:
            traces: List of DecisionTrace objects from multiple sessions
            domain: Domain label (e.g. "ankle_injury")
            min_sessions: Minimum sessions to require

        Returns:
            DecisionGraph or None if insufficient data
        """
        if len(traces) < min_sessions:
            logger.info(f"Insufficient traces: {len(traces)} < {min_sessions}")
            return None

        # 1. Filter by domain if specified
        if domain:
            traces = [t for t in traces if t.domain == domain]
            if len(traces) < min_sessions:
                return None

        # 2. Cluster similar decision paths
        clusters = self._cluster_paths(traces)

        # 3. Build consensus decision tree from clusters
        nodes, registry = self._build_consensus_tree(clusters)

        # 4. Extract priority paths by frequency
        priority_paths = self._rank_paths(clusters)

        # 5. Assemble
        root_id = next(iter(registry)) if registry else None
        graph = DecisionGraph(
            domain=domain or "mined",
            source="conversation_traces",
            source_type="mined",
            nodes=nodes,
            priority_paths=priority_paths,
            entry_node_id=root_id,
            metadata={
                "total_sessions": len(traces),
                "path_clusters": len(clusters),
                "unique_decisions": len(set(t.final_decision for t in traces)),
            },
            compiled_at=datetime.now(timezone.utc),
        )

        logger.info(
            f"Mined DecisionGraph from {len(traces)} traces: "
            f"{len(nodes)} nodes, {len(priority_paths)} paths, "
            f"{len(clusters)} clusters"
        )
        return graph

    def _cluster_paths(self, traces: List[DecisionTrace]) -> Dict[str, List[DecisionTrace]]:
        """Cluster decision traces by path similarity.

        Uses SequenceMatcher on the ordered list of decision steps.
        Returns {cluster_id: [traces]}.
        """
        if not traces:
            return {}

        clusters = {}
        assigned = set()

        for i, trace_a in enumerate(traces):
            if trace_a.session_id in assigned:
                continue

            cluster_id = f"cluster_{len(clusters)}"
            cluster = [trace_a]
            assigned.add(trace_a.session_id)

            for j, trace_b in enumerate(traces):
                if i == j or trace_b.session_id in assigned:
                    continue

                sim = self._path_similarity(trace_a.path_taken, trace_b.path_taken)
                if sim >= MERGE_THRESHOLD:
                    cluster.append(trace_b)
                    assigned.add(trace_b.session_id)

            if len(cluster) >= MIN_PATH_FREQ:
                clusters[cluster_id] = cluster

        return clusters

    def _path_similarity(self, path_a: List[str], path_b: List[str]) -> float:
        """Compute similarity between two decision paths."""
        if not path_a or not path_b:
            return 0.0
        sm = SequenceMatcher(None, path_a, path_b)
        return sm.ratio()

    def _build_consensus_tree(
        self, clusters: Dict[str, List[DecisionTrace]]
    ) -> Tuple[List[DecisionNode], Dict[str, DecisionNode]]:
        """Build a consensus decision tree from path clusters."""
        nodes = []
        registry = {}

        # Root node
        root_id = "root"
        root = DecisionNode(id=root_id, trigger="开始", action="", priority=0)
        registry[root_id] = root
        nodes.append(root)

        for cluster_id, traces in clusters.items():
            # Use the most common path in this cluster
            path_counter = Counter(tuple(t.path_taken) for t in traces)
            canonical_path, freq = path_counter.most_common(1)[0]

            prev_id = root_id
            for step_idx, step_text in enumerate(canonical_path):
                node_id = f"{cluster_id}_step{step_idx}"
                if node_id in registry:
                    prev_id = node_id
                    continue

                # Determine action from outcomes
                outcomes = [t.outcome for t in traces if t.outcome]
                action = Counter(outcomes).most_common(1)[0][0] if outcomes else ""

                node = DecisionNode(
                    id=node_id,
                    trigger=step_text[:200],
                    action=action,
                    priority=freq,
                    parent_id=prev_id,
                    children=[],
                    metadata={"cluster": cluster_id, "frequency": freq},
                )
                registry[node_id] = node
                registry[prev_id].children.append(node_id)
                prev_id = node_id

            nodes.extend(n for n in registry.values() if n.id not in {r.id for r in nodes})

        return nodes, registry

    def _rank_paths(self, clusters: Dict[str, List[DecisionTrace]]) -> List[PriorityPath]:
        """Rank decision paths by frequency."""
        paths = []
        for cluster_id, traces in clusters.items():
            all_paths = []
            for t in traces:
                all_paths.extend(t.path_taken)

            path_counter = Counter(tuple(t.path_taken) for t in traces)
            for path_tuple, freq in path_counter.most_common():
                paths.append(PriorityPath(
                    node_ids=list(path_tuple),
                    frequency=freq,
                    description=f"Mined path (n={freq}): {' → '.join(path_tuple[:5])}",
                ))

        paths.sort(key=lambda p: p.frequency, reverse=True)
        return paths[:20]


def extract_triples_from_session(
    messages: List[Dict],
) -> List[Dict]:
    """Extract question→answer→decision triples from a session's messages.

    Args:
        messages: List of {role, content} dicts from a conversation

    Returns:
        List of {question, answer, decision} triples
    """
    triples = []
    current_question = None

    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "")

        if role == "assistant" and "?" in content:
            # Assistant asked a question — starting a new triple
            current_question = content

        elif role == "user" and current_question:
            # User answered — this is the answer
            triples.append({
                "question": current_question[:300],
                "answer": content[:300],
                "decision": None,  # will be filled when assistant responds
            })
            current_question = None

        elif role == "assistant" and triples and triples[-1]["decision"] is None:
            # Assistant's response after user answer — this is the decision
            triples[-1]["decision"] = content[:500]

    return triples
