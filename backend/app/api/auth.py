"""Authentication endpoints.

This is a single-user local app. On first launch the DB is empty, so the
client must POST to /setup to create the admin account; subsequent launches
expose only /login. Sessions are stored in a signed cookie via
SessionMiddleware.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.user import LoginRequest, SetupRequest, SetupStatus, UserOut

router = APIRouter()


@router.get("/setup-status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)) -> SetupStatus:
    return SetupStatus(setup_required=db.query(User).count() == 0)


@router.post("/setup", response_model=UserOut)
def setup(payload: SetupRequest, db: Session = Depends(get_db)) -> User:
    if db.query(User).count() > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="setup already done")
    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    request.session["user_id"] = user.id
    return user


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
