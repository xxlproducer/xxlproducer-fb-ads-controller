"""User-related request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


class SetupStatus(BaseModel):
    setup_required: bool
