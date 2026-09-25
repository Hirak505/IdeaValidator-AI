from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Optional
from collections import defaultdict
import aiofiles
import os
import time

from file_parser import parse_uploaded_file, build_project_context
from judges import run_all_judges
from gemini_service import verify_environment
from utils import get_temp_path, cleanup_files

# Maximum file size allowed: 20MB
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming uploads

# Rate limiting configuration: Max 5 requests per 60 seconds per IP
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60
_request_records = defaultdict(list)


def check_rate_limit(client_ip: str) -> tuple[bool, int]:
    """Sliding-window rate limiter per client IP."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps = [t for t in _request_records[client_ip] if t > cutoff]
    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        retry_after = int(timestamps[0] + RATE_LIMIT_WINDOW_SECONDS - now) + 1
        _request_records[client_ip] = timestamps
        return False, max(1, retry_after)
    timestamps.append(now)
    _request_records[client_ip] = timestamps
    return True, 0


def get_client_ip(request: Request) -> str:
    """Extract client IP safely from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enforce pre-deploy requirement: refuse to start if required env variables missing
    verify_environment()
    yield


app = FastAPI(
    title="IdeaValidator AI",
    description="Agentic AI-powered hackathon project evaluator",
    version="1.0.0",
    lifespan=lifespan,
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Tighten CORS: restrict to specific allowed origins via environment variable
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173")
allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
async def root():
    return {"status": "ok", "message": "IdeaValidator AI is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


async def _save_upload_safely(upload_file: UploadFile, temp_path: str) -> None:
    """Stream upload into isolated temp path with strict size capping."""
    total_bytes = 0
    async with aiofiles.open(temp_path, "wb") as f:
        while True:
            chunk = await upload_file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="File exceeds maximum size limit of 20MB.",
                )
            await f.write(chunk)

    if total_bytes == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")


@app.post("/evaluate")
async def evaluate_project(
    request: Request,
    pitch_deck: Optional[UploadFile] = File(None),
    readme: Optional[UploadFile] = File(None),
    attack_mode: bool = Form(False),
):
    # Enforce Rate Limiting: max 5 requests per minute per IP
    client_ip = get_client_ip(request)
    allowed, retry_after = check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded: maximum 5 evaluations per minute."},
            headers={"Retry-After": str(retry_after)},
        )

    # Validate at least one file is provided
    if not pitch_deck and not readme:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one file: a Pitch Deck (PDF/PPTX) or a README.md file.",
        )

    temp_paths = []
    parsed_files = []

    try:
        # Save and parse pitch deck
        if pitch_deck and pitch_deck.filename:
            temp_path = get_temp_path(pitch_deck.filename)
            temp_paths.append(temp_path)
            await _save_upload_safely(pitch_deck, temp_path)

            try:
                parsed = parse_uploaded_file(temp_path, pitch_deck.filename)
                parsed_files.append(parsed)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        # Save and parse README
        if readme and readme.filename:
            temp_path = get_temp_path(readme.filename)
            temp_paths.append(temp_path)
            await _save_upload_safely(readme, temp_path)

            try:
                parsed = parse_uploaded_file(temp_path, readme.filename)
                parsed_files.append(parsed)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        # Build unified project context
        try:
            project_context = build_project_context(parsed_files)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Run AI judges
        try:
            results = await run_all_judges(project_context, attack_mode=attack_mode)
        except TimeoutError:
            raise HTTPException(status_code=504, detail="AI evaluation timed out. Please try again.")
        except EnvironmentError:
            raise HTTPException(status_code=503, detail="Service configuration unavailable.")
        except RuntimeError:
            raise HTTPException(status_code=502, detail="Evaluation service temporarily unavailable.")

        return JSONResponse(content=results)

    finally:
        # Always clean up temporary uploaded files, even on exceptions
        cleanup_files(*temp_paths)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Clean HTTP exception handler without exposing stack traces or internals."""
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Sanitized fallback exception handler.
    Never exposes stack traces, internal paths, or library details to clients.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )
