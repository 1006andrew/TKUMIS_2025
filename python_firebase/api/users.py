# src/api/users.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from .db.repos import ClientsRepo

router = APIRouter(prefix="/api/users", tags=["users"])
repo = ClientsRepo()

class UserIn(BaseModel):
    name: str
    gender: str
    age: int
    username: str
    password: str

@router.get("")
def list_users(limit: int = 20, cursor_after: Optional[str] = None):
    return repo.list(limit=limit, cursor_after=cursor_after)

@router.get("/{user_id}")
def get_user(user_id: str):
    u = repo.get_by_id(user_id)
    if not u: raise HTTPException(404, "User not found")
    return u

@router.post("")
def create_user(payload: UserIn):
    return repo.create_one(payload.model_dump())

@router.patch("/{user_id}")
def update_user(user_id: str, payload: dict):
    if not repo.get_by_id(user_id): raise HTTPException(404, "User not found")
    repo.update_one(user_id, payload); return {"ok": True}

@router.delete("/{user_id}")
def delete_user(user_id: str):
    repo.delete_one(user_id); return {"ok": True}
