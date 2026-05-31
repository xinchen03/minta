"""Decision Graph schemas — compiled from CPG or mined from conversation traces."""
from __future__ import annotations
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DecisionNode(BaseModel):
    """A single node in a decision tree."""
    id: str
    trigger: str                          # e.g. "不能负重4步"
    condition: str = ""                   # e.g. "patient cannot bear weight for 4 steps"
    action: str                           # e.g. "建议拍X光"
    parent_id: Optional[str] = None
    children: List[str] = []              # child node IDs
    priority: int = 0                     # lower = higher priority in path
    metadata: dict = {}


class PriorityPath(BaseModel):
    """A high-frequency decision path through the tree."""
    node_ids: List[str]                   # ordered list of nodes in this path
    frequency: int = 0
    description: str = ""


class DecisionGraph(BaseModel):
    """Complete decision graph for a domain."""
    domain: str                           # e.g. "ankle_injury"
    source: str = ""                      # e.g. "Stiell 1992 Ottawa Ankle Rules"
    source_type: str = "cpg"              # cpg | mined | manual
    nodes: List[DecisionNode] = []
    priority_paths: List[PriorityPath] = []
    entry_node_id: Optional[str] = None   # where to start
    metadata: dict = {}
    compiled_at: Optional[datetime] = None

    @property
    def rules(self) -> List[dict]:
        """Extract individual rules from leaf/action nodes."""
        result = []
        for node in self.nodes:
            if node.action and not node.children:
                result.append({
                    "id": node.id,
                    "trigger": node.trigger,
                    "condition": node.condition,
                    "action": node.action,
                    "priority": node.priority,
                })
        return result

    @property
    def trigger_list(self) -> List[str]:
        """All unique triggers in the graph."""
        return list(set(n.trigger for n in self.nodes if n.trigger))


class DecisionTrace(BaseModel):
    """A single execution trace through the decision graph."""
    session_id: str
    domain: str
    path_taken: List[str]                 # ordered list of node IDs traversed
    final_decision: str
    outcome: Optional[str] = None         # actual outcome (for feedback)
    timestamp: datetime = Field(default_factory=datetime.now)
