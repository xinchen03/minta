"""API Key management router — create, list, revoke."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from config import get_db
from models.api_key import ApiKey
from routers.auth import get_current_user, User
from key_utils import generate_api_key

router = APIRouter(prefix="/api/keys", tags=["api_keys"])


class CreateKeyRequest(BaseModel):
    name: str = ""


@router.post("")
def create_key(req: CreateKeyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new API key. Full key returned only once."""
    full_key, prefix, key_hash = generate_api_key()

    key = ApiKey(
        user_id=user.id,
        name=req.name.strip() or "Unnamed Key",
        key_prefix=prefix,
        key_hash=key_hash,
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    return {
        "id": key.id,
        "name": key.name,
        "key": full_key,  # returned only once
        "keyPreview": f"minta_{prefix}...",
        "createdAt": str(key.created_at) if key.created_at else "",
    }


@router.get("")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List all API keys for the current user (full keys NOT returned)."""
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).all()
    return [
        {
            "id": k.id,
            "name": k.name or "",
            "keyPreview": f"minta_{k.key_prefix}...",
            "lastUsedAt": str(k.last_used_at) if k.last_used_at else None,
            "requestCount": k.request_count or 0,
            "revoked": k.revoked,
            "createdAt": str(k.created_at) if k.created_at else "",
        }
        for k in keys
    ]


@router.delete("/{key_id}")
def revoke_key(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke an API key (soft delete)."""
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.revoked = True
    db.commit()
    return {"success": True, "id": key_id}
