"""
Authentication module for IdeaValidator-AI.

Handles password hashing (bcrypt), JWT token creation/validation,
user CRUD operations, and authentication dependency injection.
"""

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from email_validator import EmailNotValidError, validate_email
from fastapi import Cookie, Depends, HTTPException, Request

from database import close_db, get_db

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Password Hashing — bcrypt with cost factor 12
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash a password using bcrypt with work factor 12."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT Configuration
# ---------------------------------------------------------------------------
def _get_jwt_secret() -> str:
    """Retrieve JWT secret from environment. Fails loudly if missing."""
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set to a random string of at least 32 characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    return secret


JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Generic auth failure message — never reveals whether email or password is wrong
AUTH_FAILURE_MSG = "Invalid email or password."


def create_access_token(user_id: str, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": exp,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """
    Create a long-lived refresh token.
    Returns (raw_token, token_hash, expires_at).
    The raw_token is sent to the client; only the hash is stored server-side.
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return raw_token, token_hash, expires_at


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    Raises HTTPException on invalid/expired tokens.
    """
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type.")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid access token.")


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------
def validate_email_address(email: str) -> str:
    """Validate and normalize an email address. Returns normalized email."""
    try:
        result = validate_email(email, check_deliverability=False)
        return result.normalized
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="Invalid email address format.")


def validate_password_strength(password: str) -> None:
    """Enforce minimum password requirements."""
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=422,
            detail="Password must be at least 8 characters long.",
        )
    if len(password) > 128:
        raise HTTPException(
            status_code=422,
            detail="Password must not exceed 128 characters.",
        )


def validate_display_name(name: Optional[str] = "", email: str = "") -> str:
    """Validate and sanitize display name. Defaults to email prefix if not provided."""
    if not name or not name.strip():
        return email.split("@")[0] if email else "Founder"
    name = name.strip()
    if len(name) > 100:
        raise HTTPException(
            status_code=422,
            detail="Display name must not exceed 100 characters.",
        )
    return name


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------
async def create_user(email: str, password: str, display_name: Optional[str] = "") -> dict:
    """
    Create a new user with hashed password.
    Returns the user dict (without password_hash).
    Raises HTTPException 409 if email already exists.
    """
    email = validate_email_address(email)
    validate_password_strength(password)
    display_name = validate_display_name(display_name, email=email)

    user_id = uuid.uuid4().hex
    pw_hash = hash_password(password)

    db = await get_db()
    try:
        try:
            await db.execute(
                """INSERT INTO users (id, email, password_hash, display_name)
                   VALUES (?, ?, ?, ?)""",
                (user_id, email, pw_hash, display_name),
            )
            await db.commit()
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email already exists.",
                )
            raise

        cursor = await db.execute(
            "SELECT id, email, display_name, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row)
    finally:
        await close_db(db)


async def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch a user by email. Returns None if not found."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, email, password_hash, display_name, created_at FROM users WHERE email = ?",
            (email,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await close_db(db)


async def get_user_by_id(user_id: str) -> Optional[dict]:
    """Fetch a user by ID. Returns None if not found."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, email, display_name, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await close_db(db)


# ---------------------------------------------------------------------------
# Refresh Token Storage
# ---------------------------------------------------------------------------
async def store_refresh_token(
    user_id: str, token_hash: str, expires_at: datetime
) -> str:
    """Store a hashed refresh token in the database. Returns the token record ID."""
    token_id = uuid.uuid4().hex
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token_id, user_id, token_hash, expires_at.isoformat()),
        )
        await db.commit()
        return token_id
    finally:
        await close_db(db)


async def validate_refresh_token(raw_token: str) -> Optional[dict]:
    """
    Validate a refresh token by hashing and looking up in DB.
    Returns the token record if valid and not expired/revoked, else None.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked,
                      u.email, u.display_name
               FROM refresh_tokens rt
               JOIN users u ON u.id = rt.user_id
               WHERE rt.token_hash = ?""",
            (token_hash,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        record = dict(row)

        # Check if revoked
        if record.get("revoked"):
            return None

        # Check expiration
        expires_at = datetime.fromisoformat(record["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None

        return record
    finally:
        await close_db(db)


async def revoke_refresh_token(raw_token: str) -> bool:
    """Revoke a refresh token. Returns True if found and revoked."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?",
            (token_hash,),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await close_db(db)


async def revoke_all_user_tokens(user_id: str) -> int:
    """Revoke all refresh tokens for a user. Returns count revoked."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0",
            (user_id,),
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await close_db(db)


async def cleanup_expired_tokens() -> int:
    """Delete expired and revoked refresh tokens. Returns count deleted."""
    db = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "DELETE FROM refresh_tokens WHERE revoked = 1 OR expires_at < ?",
            (now,),
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await close_db(db)


# ---------------------------------------------------------------------------
# Saved Evaluations CRUD
# ---------------------------------------------------------------------------
async def save_evaluation(
    user_id: str,
    title: str,
    attack_mode: bool,
    results_json: str,
) -> dict:
    """Save an evaluation result for a user. Returns the saved record metadata."""
    eval_id = uuid.uuid4().hex
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO saved_evaluations (id, user_id, title, attack_mode, results_json)
               VALUES (?, ?, ?, ?, ?)""",
            (eval_id, user_id, title.strip() or "Untitled Evaluation", int(attack_mode), results_json),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT id, title, attack_mode, created_at FROM saved_evaluations WHERE id = ?",
            (eval_id,),
        )
        row = await cursor.fetchone()
        return dict(row)
    finally:
        await close_db(db)


async def list_user_evaluations(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """List saved evaluations for a user, ordered by newest first."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, title, attack_mode, created_at,
                      json_extract(results_json, '$.chief_judge.overall_score') as overall_score,
                      json_extract(results_json, '$.research_assisted') as research_assisted
               FROM saved_evaluations
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await close_db(db)


async def get_evaluation_by_id(eval_id: str, user_id: str) -> Optional[dict]:
    """
    Get a saved evaluation by ID, only if owned by user_id.
    Returns None if not found or not owned by this user (prevents info leakage).
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, user_id, title, attack_mode, results_json, created_at
               FROM saved_evaluations
               WHERE id = ? AND user_id = ?""",
            (eval_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await close_db(db)


async def delete_evaluation(eval_id: str, user_id: str) -> bool:
    """
    Delete a saved evaluation, only if owned by user_id.
    Returns True if deleted, False if not found or not owned.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM saved_evaluations WHERE id = ? AND user_id = ?",
            (eval_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await close_db(db)


async def count_user_evaluations(user_id: str) -> int:
    """Count total saved evaluations for a user."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM saved_evaluations WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
    finally:
        await close_db(db)


# ---------------------------------------------------------------------------
# FastAPI Dependencies for Route Protection
# ---------------------------------------------------------------------------
def get_token_from_header(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        return token if token else None
    return None


async def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency: extract and validate the access token, return current user.
    Raises 401 if token is missing, invalid, or user not found.
    """
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return user


async def get_optional_user(request: Request) -> Optional[dict]:
    """
    FastAPI dependency: optionally extract user from token.
    Returns None if no valid token is present (does not raise).
    """
    token = get_token_from_header(request)
    if not token:
        return None

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return await get_user_by_id(user_id)
    except HTTPException:
        return None
