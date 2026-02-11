from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from database import get_session
from models import User
from services.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    user_payload,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
def login(body: LoginRequest, session: Session = Depends(get_session)):
    email = body.email.strip().lower()
    password = body.password
    if not email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email cannot be empty")

    user = authenticate_user(email, password, session)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_payload(user),
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return user_payload(current_user)
