"""Task State Graph — working memory (Layer 0) for active reasoning sessions.

Working memory vs long-term memory:
  - Working memory: what we're doing RIGHT NOW (session-level, in-memory/Redis)
  - Long-term memory: what we did before (cross-session, MySQL/SQLite)
  - Procedural memory: HOW we do this type of task (compiled production rules)

This module fills the critical gap flagged by reviewers:
no working memory = long-term memory is strong but current reasoning is chaotic.
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import Lock
from schemas.task_state import TaskState, Hypothesis, DecisionStep
from schemas.decision_graph import DecisionGraph

logger = logging.getLogger(__name__)

# Optional Redis support
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class TaskStateManager:
    """Manage per-session working memory (Task State Graph).

    Default: in-memory dict. Optional: Redis-backed.
    """

    def __init__(self, redis_client=None):
        self._store: Dict[str, TaskState] = {}
        self._lock = Lock()

        if redis_client:
            self.redis = redis_client
        elif REDIS_AVAILABLE:
            try:
                self.redis = redis.Redis(host="localhost", port=6379, db=1,
                                         decode_responses=True)
                self.redis.ping()
                logger.info("TaskStateManager connected to Redis")
            except Exception:
                logger.info("TaskStateManager using in-memory store (Redis unavailable)")
                self.redis = None
        else:
            self.redis = None

    # ── Session Lifecycle ──

    def create_task(
        self,
        session_id: str,
        task_description: str,
        domain: str = "",
        initial_hypotheses: Optional[List[Hypothesis]] = None,
    ) -> TaskState:
        """Open a new reasoning task for the session."""
        state = TaskState(
            session_id=session_id,
            active_task=task_description,
            domain=domain,
            active_hypotheses=initial_hypotheses or [],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._save(session_id, state)
        logger.info(f"Task created for session {session_id}: {task_description[:60]}")
        return state

    def get_current_state(self, session_id: str) -> TaskState:
        """Get the current task state for a session."""
        state = self._load(session_id)
        if state is None:
            # Create default empty state
            state = TaskState(
                session_id=session_id,
                active_task="",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self._save(session_id, state)
        return state

    def close_task(self, session_id: str) -> Optional[DecisionGraph]:
        """Close the task and compile the decision stack into a DecisionGraph."""
        state = self._load(session_id)
        if state is None:
            return None

        # Compile decision stack into a DecisionGraph
        from schemas.decision_graph import DecisionNode, PriorityPath
        nodes = []
        for i, step in enumerate(state.decision_stack):
            node = DecisionNode(
                id=f"step_{i}",
                trigger=step.step,
                action=step.result,
                priority=i,
            )
            nodes.append(node)

        graph = DecisionGraph(
            domain=state.domain,
            source="session_trace",
            source_type="mined",
            nodes=nodes,
            priority_paths=[
                PriorityPath(
                    node_ids=[n.id for n in nodes],
                    description=f"Session {session_id}: {state.active_task}",
                )
            ],
            metadata={
                "session_id": session_id,
                "active_hypotheses": [h.dict() for h in state.active_hypotheses],
                "confirmed_hypotheses": [h.dict() for h in state.confirmed_hypotheses],
                "rejected_hypotheses": [h.dict() for h in state.rejected_hypotheses],
            },
            compiled_at=datetime.now(timezone.utc),
        )

        self._delete(session_id)
        logger.info(f"Task closed for session {session_id}, decision graph compiled")
        return graph

    # ── Hypothesis Management ──

    def add_hypothesis(self, session_id: str, hypothesis: Hypothesis) -> None:
        """Add a hypothesis to the working memory."""
        state = self.get_current_state(session_id)
        state.active_hypotheses.append(hypothesis)
        state.updated_at = datetime.now(timezone.utc)
        self._save(session_id, state)
        logger.debug(f"Hypothesis added: {hypothesis.description[:60]}")

    def confirm_hypothesis(self, session_id: str, hypothesis_id: str, evidence: str = "") -> None:
        """Confirm a hypothesis with evidence."""
        state = self.get_current_state(session_id)
        for h in state.active_hypotheses:
            if h.id == hypothesis_id:
                h.status = "confirmed"
                h.confidence = 1.0
                if evidence:
                    h.evidence.append(evidence)
                state.confirmed_hypotheses.append(h)
                state.active_hypotheses = [x for x in state.active_hypotheses if x.id != hypothesis_id]
                break
        state.updated_at = datetime.now(timezone.utc)
        self._save(session_id, state)

    def reject_hypothesis(self, session_id: str, hypothesis_id: str, reason: str = "") -> None:
        """Reject a hypothesis with reason. The rejection path IS knowledge."""
        state = self.get_current_state(session_id)
        for h in state.active_hypotheses:
            if h.id == hypothesis_id:
                h.status = "rejected"
                h.confidence = 0.0
                if reason:
                    h.evidence.append(f"Rejected: {reason}")
                state.rejected_hypotheses.append(h)
                state.active_hypotheses = [x for x in state.active_hypotheses if x.id != hypothesis_id]
                break
        state.updated_at = datetime.now(timezone.utc)
        self._save(session_id, state)
        logger.debug(f"Hypothesis rejected: {hypothesis_id} — {reason[:60]}")

    # ── Decision Stack ──

    def push_step(self, session_id: str, step: DecisionStep) -> None:
        """Push a decision step onto the stack."""
        state = self.get_current_state(session_id)
        state.decision_stack.append(step)
        state.current_step = step.step
        state.updated_at = datetime.now(timezone.utc)
        self._save(session_id, state)

    def add_question(self, session_id: str, question: str) -> None:
        """Add a pending question that needs to be answered."""
        state = self.get_current_state(session_id)
        if question not in state.pending_questions:
            state.pending_questions.append(question)
        state.updated_at = datetime.now(timezone.utc)
        self._save(session_id, state)

    def resolve_question(self, session_id: str, question: str) -> None:
        """Mark a question as resolved."""
        state = self.get_current_state(session_id)
        if question in state.pending_questions:
            state.pending_questions.remove(question)
        state.updated_at = datetime.now(timezone.utc)
        self._save(session_id, state)

    # ── Storage Backend ──

    def _save(self, session_id: str, state: TaskState) -> None:
        if self.redis is not None:
            try:
                key = f"minta:task_state:{session_id}"
                self.redis.setex(key, 3600, state.json())
                return
            except Exception as e:
                logger.warning(f"Redis save failed, falling back to memory: {e}")

        with self._lock:
            self._store[session_id] = state

    def _load(self, session_id: str) -> Optional[TaskState]:
        if self.redis is not None:
            try:
                key = f"minta:task_state:{session_id}"
                data = self.redis.get(key)
                if data:
                    return TaskState.parse_raw(data)
            except Exception as e:
                logger.warning(f"Redis load failed, falling back to memory: {e}")

        with self._lock:
            return self._store.get(session_id)

    def _delete(self, session_id: str) -> None:
        if self.redis is not None:
            try:
                key = f"minta:task_state:{session_id}"
                self.redis.delete(key)
                return
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}")

        with self._lock:
            self._store.pop(session_id, None)

    def active_sessions(self) -> int:
        """Return count of active sessions."""
        if self.redis is not None:
            try:
                keys = self.redis.keys("minta:task_state:*")
                return len(keys)
            except Exception:
                pass
        with self._lock:
            return len(self._store)
