from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from models import User, UserRole
from services.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    user_payload,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    role: UserRole
    department: str = Field(default="", max_length=80)


@router.post("/register", status_code=201)
def register(
    body: RegisterRequest,
    session: Session = Depends(get_session),
    _current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name cannot be empty")
    if not email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email cannot be empty")

    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(body.password),
        role=body.role,
        department=body.department.strip(),
    )
    session.add(user)
    try:
        session.commit()
        session.refresh(user)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to register user")

    return user_payload(user)


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
