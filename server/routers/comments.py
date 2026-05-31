"""Comments API router — community discussion on shared Context Objects."""
import re
from datetime import datetime
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime
from config import Base, get_db
from routers.auth import get_current_user, User

router = APIRouter(prefix="/api/comments", tags=["comments"])

# ── Content moderation ──
BLOCKED_PATTERNS = [
    # National security / illegal content
    r'(法轮功|falun|gong|六四|天安门|学运|藏独|疆独|台独|港独|分裂|反动)',
    # Porn / spam
    r'(色情|裸聊|约炮|一夜情|迷药|赌博|赌场|casino)',
    # Violence / weapons
    r'(枪支|弹药|炸药|毒品|冰毒|海洛因)',
    # Phone / ID harvesting
    r'(身份证|银行卡|密码|验证码|转账|汇款)',
]
BLOCKED_COMPILED = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

MAX_COMMENT_LENGTH = 1000
RATE_LIMIT_SECONDS = 3  # minimum interval between comments per user


def filter_content(text: str) -> str:
    """Check and clean comment content. Returns cleaned text or raises."""
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    if len(text) > MAX_COMMENT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Comment too long (max {MAX_COMMENT_LENGTH} chars)")
    for pattern in BLOCKED_COMPILED:
        if pattern.search(text):
            raise HTTPException(status_code=400, detail="Comment contains prohibited content")
    return text


# ── Model ──
class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Schemas ──
class CommentCreate(BaseModel):
    object_id: str
    content: str
    parent_id: Optional[int] = None


class CommentResponse(BaseModel):
    id: int
    object_id: str
    username: str
    content: str
    parent_id: Optional[int] = None
    created_at: str


# ── Rate limiting (in-memory, simple) ──
_last_comment_time: Dict[int, float] = {}


# ── Endpoints ──
@router.get("/{object_id}")
def get_comments(object_id: str, db: Session = Depends(get_db)):
    """Get all comments for a context object."""
    comments = db.query(Comment).filter(
        Comment.object_id == object_id
    ).order_by(Comment.created_at.asc()).all()

    # Build threaded structure
    roots = []
    children_map: dict[int, list] = {}
    for c in comments:
        d = {
            "id": c.id,
            "objectId": c.object_id,
            "username": c.username,
            "content": c.content,
            "parentId": c.parent_id,
            "createdAt": str(c.created_at) if c.created_at else "",
        }
        if c.parent_id is None:
            roots.append(d)
        else:
            children_map.setdefault(c.parent_id, []).append(d)

    def attach_replies(comment: dict):
        comment["replies"] = children_map.get(comment["id"], [])
        for r in comment["replies"]:
            attach_replies(r)
        return comment

    return [attach_replies(r) for r in roots]


@router.post("")
def create_comment(req: CommentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Post a comment on a shared context object."""
    content = filter_content(req.content)

    # Rate limit
    now = datetime.utcnow().timestamp()
    last = _last_comment_time.get(user.id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        raise HTTPException(status_code=429, detail="Please wait before posting another comment")
    _last_comment_time[user.id] = now

    # Verify the object exists and is public
    from models.context_object import ContextObject
    obj = db.query(ContextObject).filter(
        ContextObject.id == req.object_id,
        ContextObject.is_public == 1
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found or not public")

    comment = Comment(
        object_id=req.object_id,
        user_id=user.id,
        username=user.username,
        content=content,
        parent_id=req.parent_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {
        "id": comment.id,
        "objectId": comment.object_id,
        "username": comment.username,
        "content": comment.content,
        "parentId": comment.parent_id,
        "createdAt": str(comment.created_at) if comment.created_at else "",
    }
