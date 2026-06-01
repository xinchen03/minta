"""Email verification router — QQ SMTP verification codes."""
import random
import string
import smtplib
import time
from email.mime.text import MIMEText
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from config import get_db, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_CONFIGURED
from routers.auth import User, _check_rate_limit
from sqlalchemy import Column, Integer, String, DateTime

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── In-memory verification codes (simple, no extra table) ──
# key: email, value: {"code": str, "expires": timestamp}
_verify_codes: dict = {}


def _send_email(to: str, code: str) -> bool:
    """Send verification code via QQ SMTP."""
    msg = MIMEText(
        f"您的 Minta 邮箱验证码是：{code}\n\n5 分钟内有效。",
        "plain", "utf-8"
    )
    msg["Subject"] = "Minta 邮箱验证"
    msg["From"] = SMTP_USER
    msg["To"] = to

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception:
        return False


class SendCodeRequest(BaseModel):
    email: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


@router.post("/send-code")
def send_verification_code(req: SendCodeRequest):
    """Send email verification code."""
    _check_rate_limit(f"send-code:{req.email}", max_attempts=3, window=120)
    # Generate 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    _verify_codes[req.email] = {"code": code, "expires": time.time() + 300}

    ok = _send_email(req.email, code)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP config.")
    return {"success": True, "message": "验证码已发送"}


@router.post("/verify-code")
def verify_code(req: VerifyCodeRequest, db: Session = Depends(get_db)):
    """Verify email verification code and mark the email as verified."""
    record = _verify_codes.get(req.email)
    if not record:
        raise HTTPException(status_code=400, detail="请先请求验证码")
    if time.time() > record["expires"]:
        del _verify_codes[req.email]
        raise HTTPException(status_code=400, detail="验证码已过期，请重新请求")
    if record["code"] != req.code:
        raise HTTPException(status_code=400, detail="验证码错误")

    # Mark email as verified
    user = db.query(User).filter(User.email == req.email).first()
    if user:
        user.email_verified = 1
        db.commit()

    del _verify_codes[req.email]
    return {"success": True, "message": "邮箱已验证"}
