"""Autopilot data schemas — dataclass-based, Pydantic-free for Py3.8 compat."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal


Phase = Literal["pre_turn", "post_turn"]

Scope = Literal[
    "global:user",
    "project:current",
    "project:explicit",
    "unknown",
]

MemoryType = Literal[
    "user_preference",
    "project_constraint",
    "rule",
    "counterexample",
    "context_note",
]

UpdateOperation = Literal[
    "add_exception",
    "replace_review",
    "invalidate_review",
    "review",
]

InboxStatus = Literal[
    "pending_review",
    "approved",
    "rejected",
    "applied",
]

AutopilotLogStatus = Literal[
    "planned",
    "executed",
    "degraded",
    "failed",
    "skipped",
]


@dataclass
class Decision:
    should_run: bool = False
    confidence: float = 0.0
    reason: str = ""
    payload: Optional[Dict[str, Any]] = None


@dataclass
class PolicyInput:
    user_id: str
    phase: Phase
    user_message: str
    assistant_response: Optional[str] = None
    project_id: Optional[str] = None
    agent: Optional[str] = None


@dataclass
class PolicyResult:
    phase: Phase
    read: Decision = field(default_factory=Decision)
    write: Decision = field(default_factory=Decision)
    counter_capture: Decision = field(default_factory=Decision)
    update: Decision = field(default_factory=Decision)


# ---- API request/response schemas (Pydantic v1 compatible) ----

try:
    from pydantic import BaseModel, Field

    class PreflightRequest(BaseModel):
        user_message: str
        project_id: Optional[str] = None
        agent: Optional[str] = None

    class PreflightResponse(BaseModel):
        read_triggered: bool = False
        reason: str = ""
        memory_context: Dict[str, Any] = Field(default_factory=dict)
        log_id: Optional[str] = None
        degraded: bool = False

    class PostflightRequest(BaseModel):
        user_message: str
        assistant_response: str
        project_id: Optional[str] = None
        agent: Optional[str] = None

    class PostflightResponse(BaseModel):
        write_triggered: bool = False
        counter_capture_triggered: bool = False
        update_triggered: bool = False
        created: Dict[str, List[int]] = Field(default_factory=dict)
        reason: str = ""
        log_id: Optional[str] = None
        degraded: bool = False

    class StatusCheck(BaseModel):
        label: str
        passed: bool
        detail: str = ""

    class AutopilotStatus(BaseModel):
        active: bool = False
        mode: str = "manual_mcp"
        agent: Optional[str] = None
        checks: List[StatusCheck] = Field(default_factory=list)

except ImportError:
    # Fallback: plain dicts if Pydantic not available
    pass
