"""Auth router — register, login, JWT."""
from datetime import datetime, timedelta
from typing import Optional
import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from pydantic import BaseModel, validator
import re
from config import get_db, Base, SMTP_CONFIGURED
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

# ── User model (mirrors existing `users` table) ──
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    email_verified = Column(Integer, default=0)
    experiment_condition = Column(String(20), nullable=True)  # "control" | "treatment" | NULL
    created_at = Column(DateTime, server_default=func.now())

# ── Config ──
import os
import random
from config import _load_or_generate
_SECRET_KEY_FALLBACK = _load_or_generate(".minta_jwt_secret", nbytes=32)
SECRET_KEY = os.environ.get("MINTA_JWT_SECRET", _SECRET_KEY_FALLBACK)
if SECRET_KEY == _SECRET_KEY_FALLBACK and os.environ.get("MINTA_ENV", "").lower() in ("production", "prod"):
    raise RuntimeError("MINTA_JWT_SECRET must be set in production! Run: python -c 'import secrets; print(secrets.token_urlsafe(32))'")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("MINTA_JWT_EXPIRE_MINUTES", "1440"))  # 24 hours

security = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return _bcrypt.checkpw(password.encode(), password_hash.encode())


# ── Schemas ──
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @validator("username")
    def validate_username(cls, v):
        if len(v) < 2 or len(v) > 30:
            raise ValueError("Username must be 2–30 characters")
        if not re.match(r"^[a-zA-Z0-9_一-鿿]+$", v):
            raise ValueError("Username: letters, numbers, underscores, Chinese only")
        return v

    @validator("password")
    def validate_password(cls, v):
        if len(v) < 6 or len(v) > 128:
            raise ValueError("Password must be 6–128 characters")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    username: str
    experimentCondition: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar_url: Optional[str] = None
    email_verified: int = 0
    experiment_condition: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    email: Optional[str] = None
    avatar_url: Optional[str] = None


# ── Rate limiter (in-memory, simple) ──
_RATE_LIMIT: dict = {}  # key -> [count, window_start]


def _check_rate_limit(key: str, max_attempts: int = 5, window: int = 60):
    """Check rate limit. Raises HTTPException if exceeded."""
    from time import time as _time
    now = _time()
    entry = _RATE_LIMIT.get(key)
    if not entry or now - entry[1] > window:
        _RATE_LIMIT[key] = [1, now]
        return
    entry[0] += 1
    if entry[0] > max_attempts:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {window}s.")


# ── Helpers ──
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    # ── API Key authentication ──
    if x_api_key:
        if not x_api_key.startswith("minta_"):
            raise HTTPException(status_code=401, detail="Invalid API key format")
        prefix = x_api_key[len("minta_"):len("minta_") + 8]
        from models.api_key import ApiKey
        from key_utils import verify_api_key
        key_record = db.query(ApiKey).filter(
            ApiKey.key_prefix == prefix,
            ApiKey.revoked == False,
        ).first()
        if not key_record or not verify_api_key(x_api_key, key_record.key_hash):
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        # Update usage tracking
        key_record.last_used_at = datetime.utcnow()
        key_record.request_count = (key_record.request_count or 0) + 1
        db.commit()
        user = db.query(User).filter(User.id == key_record.user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    # ── JWT Bearer authentication ──
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Helper: log activity ──
from models.activity_log import ActivityLog
from models.context_object import ContextObject
from models.inbox import InboxItem
import uuid


def _log_activity(db: Session, user_id: int, event_type: str, detail: str = None):
    try:
        db.add(ActivityLog(user_id=user_id, event_type=event_type, detail=detail))
        db.commit()
    except Exception:
        db.rollback()


def _seed_starter_context(db: Session, user):
    """Auto-write starter context + inbox example for new users."""
    starters = []
    try:
        # Context 1: Welcome
        c1 = ContextObject(
            id=str(uuid.uuid4()),
            user_id=user.id,
            type="preference",
            title="欢迎使用 Minta",
            summary="这是你的第一条上下文记录。Minta 会自动管理你的 AI 记忆。",
            body="Minta 会在对话中自动读取相关上下文、捕获反例和偏好。你可以在 Inbox 中审核确认后再写入知识库。",
            tags=["onboarding", "starter"],
            source="manual",
            confidence=5,
            owner_name=user.username,
        )
        db.add(c1)
        starters.append(c1)
        # Context 2: Knowledge Base intro
        c2 = ContextObject(
            id=str(uuid.uuid4()),
            user_id=user.id,
            type="ai_brief",
            title="你的 AI 记忆工作台",
            summary="这里就是你的知识库——存放偏好、规则、项目背景、经验教训。",
            body="Minta 把记忆分成 9 种类型（偏好、工作流、项目上下文、决策标准、经验教训、写作风格、规则、AI 简报、职业档案）。每种类型有不同用途。你可以在这里浏览、搜索、编辑、分享。AI 对话时，Minta 会根据话题自动捡取相关记忆注入上下文。",
            tags=["onboarding", "starter", "knowledge-base"],
            source="manual",
            confidence=5,
            owner_name=user.username,
        )
        db.add(c2)
        starters.append(c2)
        # Context 3: Autopilot guide
        c3 = ContextObject(
            id=str(uuid.uuid4()),
            user_id=user.id,
            type="workflow",
            title="如何使用 Autopilot",
            summary="配置 MCP 后，AI 会自动调用 Autopilot 管理记忆。",
            body="回答前自动读取记忆（preflight），回答后自动判断是否需要写入或捕获反例（postflight）。所有操作先进入 Inbox 等你审核，不会自动写入——你始终拥有最终决定权。",
            tags=["onboarding", "autopilot"],
            source="manual",
            confidence=5,
            owner_name=user.username,
        )
        db.add(c3)
        starters.append(c3)
        # Inbox: sample counter-example
        db.add(InboxItem(
            user_id=user.id,
            text="[示例] 这是一条示例反例——当 AI 出错时，Minta 会自动捕获纠正信号。你可以在 Inbox 面板中审核、编辑类型和标签，然后确认归档或丢弃。",
            type="lesson_learned",
            confidence=0.5,
            tags=["onboarding", "sample", "counter-example"],
            status="pending",
        ))
        # Best-effort conflict embeddings for starter objects (384-d input)
        from services import vector_ops
        for c in starters:
            vector_ops.apply_conflict_embedding(c)
        db.commit()
        # Best-effort vector indexing for the starter objects (search visibility)
        for c in starters:
            vector_ops.index_object(c.id, vector_ops.compose_text(c.title, c.summary, c.body),
                                    user.id, c.type, c.status)
    except Exception:
        db.rollback()


# ── Endpoints ──
@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    _check_rate_limit(f"register:{req.username}", max_attempts=3, window=300)
    if db.query(User).filter((User.username == req.username) | (User.email == req.email)).first():
        raise HTTPException(status_code=400, detail="Username or email already exists")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        email_verified=1,  # auto-verify always (email verification disabled pre-commercialization)
        experiment_condition=random.choice(["control", "treatment"]),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # ── Starter context for new users ──
    _seed_starter_context(db, user)

    return UserResponse(id=user.id, username=user.username, email=user.email, experiment_condition=user.experiment_condition)


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    _check_rate_limit(f"login:{req.username}", max_attempts=10, window=60)
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(data={"sub": str(user.id)})
    _log_activity(db, user.id, "login")
    return TokenResponse(accessToken=token, username=user.username, experimentCondition=user.experiment_condition)


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, username=user.username, email=user.email, avatar_url=user.avatar_url, email_verified=user.email_verified, experiment_condition=user.experiment_condition)


@router.patch("/me")
def update_me(req: UpdateProfileRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.email is not None:
        user.email = req.email
    if req.avatar_url is not None:
        user.avatar_url = req.avatar_url
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, username=user.username, email=user.email, avatar_url=user.avatar_url, email_verified=user.email_verified)
