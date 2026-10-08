import logging

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.user import Token, UserCreate, UserOut
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    username = payload.username.lower()
    email = payload.email.lower()
    exists = db.scalar(select(User.id).where(or_(User.username == username, User.email == email)))
    if exists:
        raise ConflictError("Username or email is already registered")

    user = User(username=username, email=email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.flush()
    record_audit(db, "user.register", user_id=user.id, entity_type="user", entity_id=user.id, ip_address=client_ip(request))
    db.commit()
    return user


@router.post("/login", response_model=Token)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow. `username` accepts either the username or the email address."""
    identifier = form.username.strip().lower()
    user = db.scalar(select(User).where(or_(User.username == identifier, User.email == identifier)))
    if user is None or not user.is_active or not verify_password(form.password, user.hashed_password):
        record_audit(db, "user.login_failed", details={"identifier": identifier[:100]}, ip_address=client_ip(request))
        db.commit()
        raise UnauthorizedError("Incorrect username or password")

    record_audit(db, "user.login", user_id=user.id, entity_type="user", entity_id=user.id, ip_address=client_ip(request))
    db.commit()
    return Token(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
