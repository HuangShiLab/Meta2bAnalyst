"""
Authentication and user-management API routes.

Login is open; everything user-related beyond that requires a valid token,
and user creation/listing/deletion is admin-only. Students get pre-created
accounts (bulk CSV import via backend/scripts/create_users.py or POST
/auth/users), so there is deliberately no public registration endpoint.
"""
import datetime
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.database import get_db
from app.models import DataFile, Session as SessionModel, User
from app.services.auth import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    quota_mb: Optional[int]
    created_at: Optional[datetime.datetime]
    last_login_at: Optional[datetime.datetime]


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6)
    role: str = Field(default="student", pattern="^(admin|student)$")
    quota_mb: Optional[int] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


class UsageOut(BaseModel):
    used_bytes: int
    quota_mb: int
    session_count: int


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        role=u.role,
        quota_mb=u.quota_mb,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
    )


@router.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        # Same message either way: do not leak which usernames exist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    user.last_login_at = datetime.datetime.utcnow()
    db.commit()
    logger.info("User %s logged in", user.username)
    return LoginResponse(token=create_token(user), user=_user_out(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.get("/auth/me/usage", response_model=UsageOut)
def my_usage(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """Storage usage for the "My Data" page: bytes owned + effective quota."""
    used = (
        db.query(func.coalesce(func.sum(DataFile.file_size), 0))
        .join(SessionModel, DataFile.session_id == SessionModel.id)
        .filter(SessionModel.user_id == user.id)
        .scalar()
    )
    session_count = (
        db.query(func.count(SessionModel.id))
        .filter(SessionModel.user_id == user.id)
        .scalar()
    )
    return UsageOut(
        used_bytes=int(used or 0),
        quota_mb=user.quota_mb or settings.USER_QUOTA_MB,
        session_count=int(session_count or 0),
    )


@router.post("/auth/change-password")
def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    if not verify_password(request.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password incorrect")
    user.password_hash = hash_password(request.new_password)
    db.commit()
    return {"status": "ok"}


@router.get("/auth/users", response_model=List[UserOut])
def list_users(_admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    return [_user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/auth/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    request: CreateUserRequest,
    _admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
        role=request.role,
        quota_mb=request.quota_mb,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Admin created user %s (role=%s)", user.username, user.role)
    return _user_out(user)


@router.delete("/auth/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    # Sessions survive their owner: SET NULL turns them into shared sessions
    # rather than deleting anyone's data with the account.
    db.delete(user)
    db.commit()
    return {"status": "deleted", "username": user.username}


def ensure_default_admin(db: DBSession) -> None:
    """Seed the first admin account when the users table is empty.

    Password comes from settings.ADMIN_PASSWORD; without it a random one is
    generated and printed to the log once (change it after first login).
    """
    if db.query(User).count() > 0:
        return
    password = settings.ADMIN_PASSWORD
    if not password:
        import secrets

        password = secrets.token_urlsafe(10)
        logger.warning("=" * 60)
        logger.warning("No ADMIN_PASSWORD set. Initial admin credentials:")
        logger.warning("  username: %s  password: %s", settings.ADMIN_USERNAME, password)
        logger.warning("Change this password immediately after first login.")
        logger.warning("=" * 60)
    admin = User(
        username=settings.ADMIN_USERNAME,
        password_hash=hash_password(password),
        role="admin",
    )
    db.add(admin)
    db.commit()
    logger.info("Seeded default admin account '%s'", settings.ADMIN_USERNAME)
