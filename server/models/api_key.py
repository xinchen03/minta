"""SQLAlchemy model for api_keys table."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from config import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    key_prefix = Column(String(16), nullable=False)
    key_hash = Column(String(255), nullable=False)
    name = Column(String(100), default="")
    last_used_at = Column(DateTime, nullable=True)
    request_count = Column(Integer, default=0)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "keyPrefix": f"minta_{self.key_prefix}...",
            "name": self.name or "",
            "lastUsedAt": str(self.last_used_at) if self.last_used_at else None,
            "revoked": self.revoked,
            "createdAt": str(self.created_at) if self.created_at else "",
        }
