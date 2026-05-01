"""FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # session referencing a deleted user
        request.session.clear()
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
