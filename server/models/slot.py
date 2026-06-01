"""SQLAlchemy model for slots table."""
from sqlalchemy import Column, String, Text, Integer, Boolean, Float, Enum as SAEnum, DateTime
from sqlalchemy.sql import func
from config import Base


class Slot(Base):
    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    label = Column(String(64), nullable=False)
    content = Column(Text, nullable=False)
    size_limit = Column(Integer, nullable=False, default=2000)
    pinned = Column(Boolean, nullable=False, default=True)
    scope = Column(SAEnum("global", "project", name="slot_scope"), nullable=False, default="global")
    auto_reflected = Column(Boolean, nullable=False, default=False)
    retention_score = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "label": self.label,
            "content": self.content or "",
            "sizeLimit": self.size_limit,
            "pinned": bool(self.pinned),
            "scope": self.scope,
            "autoReflected": bool(self.auto_reflected),
            "retentionScore": self.retention_score,
            "createdAt": str(self.created_at) if self.created_at else "",
            "updatedAt": str(self.updated_at) if self.updated_at else "",
        }


DEFAULT_SLOTS = [
    {
        "label": "persona",
        "content": "",
        "size_limit": 1000,
        "pinned": True,
        "scope": "global",
        "description": "用户身份/角色/背景。写一次，很少改。",
    },
    {
        "label": "preferences",
        "content": "",
        "size_limit": 2000,
        "pinned": True,
        "scope": "global",
        "description": "用户偏好——风格、工具、命名习惯、沟通方式。",
    },
    {
        "label": "knowledge",
        "content": "",
        "size_limit": 3000,
        "pinned": True,
        "scope": "project",
        "description": "项目背景、架构决策、领域知识。",
    },
    {
        "label": "counter_examples",
        "content": "",
        "size_limit": 2000,
        "pinned": True,
        "scope": "global",
        "description": "反例教训——上次做错了什么，正确做法是什么。",
    },
    {
        "label": "skills",
        "content": "",
        "size_limit": 2000,
        "pinned": True,
        "scope": "global",
        "description": "可复用技能/工作流模板摘要。",
    },
    {
        "label": "pending",
        "content": "",
        "size_limit": 1500,
        "pinned": True,
        "scope": "project",
        "description": "未完成事项、TODO、承诺但未交付的东西。",
    },
    {
        "label": "rules",
        "content": "",
        "size_limit": 3000,
        "pinned": True,
        "scope": "project",
        "description": "前置规则——宪章原则、编码规范、设计约束。手动维护，不参与自动反射。",
    },
]
