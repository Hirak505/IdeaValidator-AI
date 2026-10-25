"""
Authentication API routes for IdeaValidator-AI.

Endpoints:
  POST /auth/register  — Create a new user account
  POST /auth/login     — Authenticate and issue tokens
  GET  /auth/me        — Get current user info
  POST /auth/refresh   — Refresh access token via HttpOnly cookie
  POST /auth/logout    — Revoke refresh token
"""

import logging
import os
import time
from collections import defaultdict

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import (
    AUTH_FAILURE_MSG,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    create_user,
    get_current_user,
    get_user_by_email,
    revoke_refresh_token,
    store_refresh_token,
    validate_refresh_token,
    verify_password,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Auth-specific rate limiting (stricter than evaluation: 10 req/60s per IP)
# ---------------------------------------------------------------------------
_AUTH_RATE_LIMIT_REQUESTS = 10
_AUTH_RATE_LIMIT_WINDOW = 60
_auth_request_records: dict[str, list[float]] = defaultdict(list)


def _check_auth_rate_limit(client_ip: str) -> tuple[bool, int]:
    """Sliding-window rate limiter for auth endpoints."""
    now = time.time()
    cutoff = now - _AUTH_RATE_LIMIT_WINDOW

    timestamps = [t for t in _auth_request_records[client_ip] if t > cutoff]
    if len(timestamps) >= _AUTH_RATE_LIMIT_REQUESTS:
        retry_after = int(timestamps[0] + _AUTH_RATE_LIMIT_WINDOW - now) + 1
        _auth_request_records[client_ip] = timestamps
        return False, max(1, retry_after)
    timestamps.append(now)
    _auth_request_records[client_ip] = timestamps
    return True, 0


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Cookie Configuration
# ---------------------------------------------------------------------------
_REFRESH_COOKIE_NAME = "iv_refresh_token"
_CSRF_COOKIE_NAME = "iv_csrf_token"


def _is_production() -> bool:
    """Check if running in production mode."""
    return os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Set the HttpOnly refresh token cookie."""
    is_prod = _is_production()
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=is_prod,  # True in production (HTTPS), False in dev (HTTP)
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    is_prod = _is_production()
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path="/auth",
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = ""


class LoginRequest(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    """Create a new user account."""
    client_ip = _get_client_ip(request)
    allowed, retry_after = _check_auth_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
            headers={"Retry-After": str(retry_after)},
        )

    user = await create_user(
        email=body.email,
        password=body.password,
        display_name=body.display_name,
    )

    # Issue tokens on registration (auto-login)
    access_token = create_access_token(user["id"], user["email"])
    raw_refresh, token_hash, expires_at = create_refresh_token(user["id"])
    await store_refresh_token(user["id"], token_hash, expires_at)

    response = JSONResponse(
        status_code=201,
        content={
            "user": {
                "id": user["id"],
                "email": user["email"],
                "display_name": user["display_name"],
                "created_at": user.get("created_at"),
            },
            "access_token": access_token,
            "token_type": "bearer",
        },
    )
    _set_refresh_cookie(response, raw_refresh)
    return response


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """Authenticate user and issue tokens."""
    client_ip = _get_client_ip(request)
    allowed, retry_after = _check_auth_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
            headers={"Retry-After": str(retry_after)},
        )

    # Generic failure: don't reveal whether email or password is wrong
    user = await get_user_by_email(body.email)
    if not user:
        raise HTTPException(status_code=401, detail=AUTH_FAILURE_MSG)

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail=AUTH_FAILURE_MSG)

    # Issue tokens
    access_token = create_access_token(user["id"], user["email"])
    raw_refresh, token_hash, expires_at = create_refresh_token(user["id"])
    await store_refresh_token(user["id"], token_hash, expires_at)

    response = JSONResponse(
        content={
            "user": {
                "id": user["id"],
                "email": user["email"],
                "display_name": user["display_name"],
                "created_at": user.get("created_at"),
            },
            "access_token": access_token,
            "token_type": "bearer",
        }
    )
    _set_refresh_cookie(response, raw_refresh)
    return response


@router.get("/me")
async def me(request: Request):
    """Get the current authenticated user's profile."""
    user = await get_current_user(request)
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "created_at": user.get("created_at"),
    }


@router.post("/refresh")
async def refresh(request: Request):
    """
    Refresh the access token using the HttpOnly refresh cookie.
    Implements token rotation: old refresh token is revoked and a new one issued.
    """
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh token not found.")

    record = await validate_refresh_token(raw_token)
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    user_id = record["user_id"]
    email = record["email"]
    display_name = record["display_name"]

    # Revoke old token (rotation)
    await revoke_refresh_token(raw_token)

    # Issue new tokens
    access_token = create_access_token(user_id, email)
    new_raw_refresh, new_token_hash, new_expires_at = create_refresh_token(user_id)
    await store_refresh_token(user_id, new_token_hash, new_expires_at)

    response = JSONResponse(
        content={
            "user": {
                "id": user_id,
                "email": email,
                "display_name": display_name,
            },
            "access_token": access_token,
            "token_type": "bearer",
        }
    )
    _set_refresh_cookie(response, new_raw_refresh)
    return response


@router.post("/logout")
async def logout(request: Request):
    """Revoke the refresh token and clear the cookie."""
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if raw_token:
        await revoke_refresh_token(raw_token)

    response = JSONResponse(content={"status": "logged_out"})
    _clear_refresh_cookie(response)
    return response
