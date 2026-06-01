"""SQLAlchemy model for skills table."""
import json
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON
from sqlalchemy.sql import func
from config import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(String(100), primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    name = Column(String(100), nullable=False)
    name_zh = Column(String(100), nullable=False)
    group = Column(String(50), nullable=False)
    color = Column(String(50), default="")
    icon_bg = Column(String(100), default="")
    icon = Column(String(50), default="")
    description = Column(Text, default="")
    tags = Column(JSON, default=list)
    is_public = Column(Integer, default=0)
    owner_name = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "nameZh": self.name_zh,
            "group": self.group,
            "color": self.color,
            "iconBg": self.icon_bg,
            "icon": self.icon,
            "description": self.description,
            "tags": self._parse_tags(),
            "isPublic": bool(self.is_public) if self.is_public is not None else False,
            "ownerName": self.owner_name or None,
        }

    def _parse_tags(self):
        t = self.tags
        if t is None:
            return []
        if isinstance(t, str):
            try:
                return json.loads(t)
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(t, list):
            return t
        return []
