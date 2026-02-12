from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Session, select

from database import get_session
from models import User, UserRole

PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = int(os.getenv("CLAVIS_TOKEN_TTL_SECONDS", str(12 * 60 * 60)))
AUTH_SECRET = os.getenv("CLAVIS_AUTH_SECRET", "clavis-dev-secret-change-me")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * ((4 - len(encoded) % 4) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{_b64url_encode(salt)}${_b64url_encode(digest)}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iter_raw, salt_raw, digest_raw = password_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False

    try:
        iterations = int(iter_raw)
        salt = _b64url_decode(salt_raw)
        expected = _b64url_decode(digest_raw)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_access_token(user: User) -> str:
    if user.id is None:
        raise ValueError("User id is required to issue token")

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "email": user.email,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    message = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(AUTH_SECRET.encode(), message, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_access_token(token: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    message = f"{header_b64}.{payload_b64}".encode()
    expected_signature = hmac.new(AUTH_SECRET.encode(), message, hashlib.sha256).digest()
    try:
        provided_signature = _b64url_decode(signature_b64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature") from exc
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode())
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return payload


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth scheme")
    token = authorization[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return token


def get_user_from_token(token: str, session: Session) -> User:
    payload = decode_access_token(token)
    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    try:
        user_id = int(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or missing")
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    token = extract_bearer_token(authorization)
    return get_user_from_token(token, session)


def require_roles(*roles: UserRole | str) -> Callable:
    allowed = {role.value if isinstance(role, UserRole) else str(role) for role in roles}

    def _path_int(request: Request, key: str) -> int | None:
        raw = request.path_params.get(key)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def _dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> User:
        if current_user.role.value not in allowed:
            try:
                from services.safety_engine import SafetySeverity, create_safety_event

                allowed_text = ", ".join(sorted(allowed))
                await create_safety_event(
                    session,
                    patient_id=_path_int(request, "patient_id"),
                    action_id=_path_int(request, "action_id"),
                    event_type="ROLE_VIOLATION",
                    severity=SafetySeverity.WARNING,
                    description=(
                        f"Role '{current_user.role.value}' blocked on {request.method} {request.url.path}. "
                        f"Allowed roles: {allowed_text}"
                    ),
                    blocked=True,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not allowed",
            )
        return current_user

    return _dependency


def authenticate_user(email: str, password: str, session: Session) -> User | None:
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "department": user.department,
    }
