"""
Lightweight authentication for the multi-user (classroom) deployment.

Stdlib-only on purpose: PBKDF2-HMAC-SHA256 for passwords and an HMAC-SHA256
signed token, so the backend image needs no rebuild for auth libraries.
Tokens are Bearer tokens with an expiry claim; the signing secret comes from
settings.AUTH_SECRET (set AUTH_SECRET in the environment for production —
the default is a random per-boot secret, which simply invalidates all tokens
on restart).
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 120_000
_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_HOURS", "72")) * 3600


def _secret() -> bytes:
    secret = settings.AUTH_SECRET
    if not secret:
        # Random per boot: secure by default, at the cost of invalidating
        # tokens on restart. Set AUTH_SECRET to keep tokens across restarts.
        secret = _bootstrap_secret()
    return secret.encode()


_bootstrapped: Optional[str] = None


def _bootstrap_secret() -> str:
    global _bootstrapped
    if _bootstrapped is None:
        _bootstrapped = base64.urlsafe_b64encode(os.urandom(32)).decode()
        logger.warning(
            "AUTH_SECRET not set; using a random per-boot secret. "
            "All login tokens will be invalidated on restart."
        )
    return _bootstrapped


# ── Passwords ────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


# ── Tokens ───────────────────────────────────────────────────────────────


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        body, sig = token.split(".")
        expected = _b64e(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except Exception:
        return None


# ── FastAPI dependencies ─────────────────────────────────────────────────


def _extract_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return request.cookies.get("m2b_token")


def get_current_user(
    request: Request, db: DBSession = Depends(get_db)
) -> User:
    token = _extract_token(request)
    payload = verify_token(token) if token else None
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account disabled or removed",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


def user_can_access_session(user: User, session) -> bool:
    """Ownership rule shared by the route layer and the auth middleware:
    admins and the owner always may; sessions with no owner (demo data and
    pre-auth legacy data) are shared with every authenticated user."""
    if user.role == "admin":
        return True
    owner_id = getattr(session, "user_id", None)
    return owner_id is None or owner_id == user.id
