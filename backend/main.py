from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Optional
from collections import defaultdict
import aiofiles
import json
import os
import time

from file_parser import parse_uploaded_file, build_project_context
from judges import run_all_judges
from gemini_service import verify_environment
from utils import get_temp_path, cleanup_files, cleanup_stale_temp_files
import research as research_module

# Maximum file size allowed: 20MB
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming uploads

import ipaddress

# Rate limiting configuration: Max 5 requests per 60 seconds per IP
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60
_request_records = defaultdict(list)
_last_prune_time = 0.0

# Explicitly trusted proxy IPs and CIDR networks (e.g. internal ingress / load balancer subnets)
raw_trusted_proxies = os.getenv("TRUSTED_PROXIES", "")
TRUSTED_PROXIES = {p.strip() for p in raw_trusted_proxies.split(",") if p.strip()}


def _parse_trusted_proxies(proxy_input: str | set | list) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse comma-separated IPs, CIDR ranges, or sets into ipaddress networks."""
    networks = []
    if isinstance(proxy_input, str):
        items = proxy_input.split(",")
    else:
        items = list(proxy_input)

    for item in items:
        stripped = str(item).strip()
        if stripped:
            try:
                networks.append(ipaddress.ip_network(stripped, strict=False))
            except ValueError:
                pass
    return networks


def _is_trusted_proxy(ip_str: str) -> bool:
    """Check if an IP address falls within configured trusted proxy networks or IPs."""
    if not ip_str or ip_str == "unknown":
        return False
    # Check both module-level TRUSTED_PROXIES and current os.environ
    env_proxies = os.getenv("TRUSTED_PROXIES", "")
    sources = [TRUSTED_PROXIES]
    if env_proxies:
        sources.append(env_proxies)

    for source in sources:
        trusted_networks = _parse_trusted_proxies(source)
        if trusted_networks:
            try:
                addr = ipaddress.ip_address(ip_str)
                if any(addr in net for net in trusted_networks):
                    return True
            except ValueError:
                pass
    return False


def check_rate_limit(client_ip: str) -> tuple[bool, int]:
    """Sliding-window rate limiter per client IP with bounded stale-entry eviction."""
    global _last_prune_time
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    # Evict stale IP entries with a 10s cooldown to prevent redundant work under high request volume
    if len(_request_records) > 500 and (now - _last_prune_time) > 10.0:
        _last_prune_time = now
        stale_ips = [ip for ip, ts in _request_records.items() if not ts or ts[-1] <= cutoff]
        for ip in stale_ips:
            del _request_records[ip]

    timestamps = [t for t in _request_records[client_ip] if t > cutoff]
    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        retry_after = int(timestamps[0] + RATE_LIMIT_WINDOW_SECONDS - now) + 1
        _request_records[client_ip] = timestamps
        return False, max(1, retry_after)
    timestamps.append(now)
    _request_records[client_ip] = timestamps
    return True, 0


def get_client_ip(request: Request) -> str:
    """
    Extract client IP safely from request.
    Only trusts X-Forwarded-For if request comes directly from a trusted proxy (supports CIDR and IPv4/IPv6).
    Walks forwarded chain right-to-left to determine the true client IP without accepting spoofed leftmost hops.
    """
    direct_ip = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(direct_ip):
        return direct_ip

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return direct_ip

    # Split hops: rightmost hops are closest to our trusted reverse proxy
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    if not hops:
        return direct_ip

    # Walk backwards from closest hop to find the first untrusted client IP
    client_ip = hops[0]
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop):
            client_ip = hop
            break
    return client_ip


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enforce pre-deploy requirement: refuse to start if required env variables missing
    verify_environment()
    # Prune any stale upload files left from previous crashed sessions
    cleanup_stale_temp_files(max_age_seconds=3600)
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

    # Restrict file permissions on supported systems (owner-read/write only)
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass


@app.post("/evaluate")
async def evaluate_project(
    request: Request,
    pitch_deck: Optional[UploadFile] = File(None),
    readme: Optional[UploadFile] = File(None),
    attack_mode: bool = Form(False),
    research_request_id: Optional[str] = Form(None),
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

        # Resolve optional Mythos research linked to this idea and request ID
        external_research_block = None
        if research_request_id and research_request_id.strip():
            imported = research_module.get_imported_research(
                research_request_id.strip(), project_context
            )
            if imported:
                external_research_block = research_module.format_research_for_prompt(imported)

        # Run AI judges
        try:
            results = await run_all_judges(
                project_context,
                attack_mode=attack_mode,
                external_research=external_research_block,
            )
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


@app.post("/research/request")
async def create_research_request(
    request: Request,
    pitch_deck: Optional[UploadFile] = File(None),
    readme: Optional[UploadFile] = File(None),
):
    """
    Create a new Mythos research request bound to the submitted idea.

    Returns:
    - request_id: include in Mythos research prompt
    - auth_token: keep client-side ONLY; never share in the research prompt; required to import research
    - expires_in: seconds until this request expires
    - research_prompt: copyable Mythos prompt (request_id embedded, auth_token excluded)
    """
    client_ip = get_client_ip(request)
    allowed, retry_after = check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please wait before creating another research request."},
            headers={"Retry-After": str(retry_after)},
        )

    if not pitch_deck and not readme:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one file to create a research request.",
        )

    temp_paths = []
    parsed_files = []

    try:
        if pitch_deck and pitch_deck.filename:
            temp_path = get_temp_path(pitch_deck.filename)
            temp_paths.append(temp_path)
            await _save_upload_safely(pitch_deck, temp_path)
            try:
                parsed_files.append(parse_uploaded_file(temp_path, pitch_deck.filename))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        if readme and readme.filename:
            temp_path = get_temp_path(readme.filename)
            temp_paths.append(temp_path)
            await _save_upload_safely(readme, temp_path)
            try:
                parsed_files.append(parse_uploaded_file(temp_path, readme.filename))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        try:
            project_context = build_project_context(parsed_files)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        try:
            req = research_module.create_research_request(project_context)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Build a short idea summary for the Mythos prompt (first 1500 chars of context)
        idea_summary = project_context[:1500]
        research_prompt = research_module.build_mythos_research_prompt(
            req["request_id"], idea_summary
        )

        return JSONResponse(content={
            "request_id": req["request_id"],
            "auth_token": req["auth_token"],  # raw token — client must store this securely
            "expires_in": req["expires_in"],
            "research_prompt": research_prompt,
        })

    finally:
        cleanup_files(*temp_paths)


@app.post("/research/import")
async def import_research(
    request: Request,
    request_id: str = Form(...),
    research_json: str = Form(...),
):
    """
    Import Mythos research JSON for an existing pending request.

    Requires Authorization: Bearer <auth_token> header.
    The auth_token was returned when the research request was created.
    This endpoint is single-use: duplicate imports are rejected.

    The research_json must conform to schema_version 1.0.
    All imported fields are treated as untrusted external data.
    """
    # Extract bearer token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header with Bearer token is required.",
        )
    raw_token = auth_header[len("Bearer "):].strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="Bearer token is missing or empty.")

    # Parse JSON payload
    try:
        payload = json.loads(research_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e.msg}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Research payload must be a JSON object.")

    # Retrieve the idea-bound project_context to verify binding
    # We need the idea hash from the stored entry; look it up without token first
    entry = research_module.get_pending_request(request_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Research request not found or has expired.")

    # We cannot reconstruct project_context from the hash (one-way), so we ask research module
    # to perform constant-time verification using a sentinel empty string — the real
    # binding check happens via idea_hash comparison inside import_research().
    # Since we stored idea_hash = sha256(project_context), we pass a dummy context and
    # let import_research raise if it doesn't match. But we don't know the context here.
    # Instead we verify in two steps: token auth first, then attachment via evaluate.
    #
    # DESIGN NOTE: The import endpoint trusts the stored idea_hash binding that was
    # created during /research/request. Token verification proves the caller is the
    # same browser session that created the request; the idea binding is enforced in
    # get_imported_research() at /evaluate time when both context and request_id are present.
    #
    # To verify token only (not idea), we import with a special bypass using the stored hash:
    from research import _hash_token, _pending_requests, _store_lock
    import hashlib, secrets as _sec

    with _store_lock:
        _entry = _pending_requests.get(request_id)
        if _entry is None:
            raise HTTPException(status_code=404, detail="Research request not found or has expired.")
        if not _sec.compare_digest(_hash_token(raw_token), _entry["token_hash"]):
            raise HTTPException(status_code=401, detail="Invalid capability token.")
        if _entry["imported"]:
            raise HTTPException(status_code=409, detail="Research has already been imported for this request.")
        # Validate payload
        try:
            from research import _validate_research_payload
            validated = _validate_research_payload(payload, request_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        # Commit
        _entry["imported"] = True
        _entry["research"] = validated
        _pending_requests[request_id] = _entry

    return JSONResponse(content={
        "status": "imported",
        "request_id": request_id,
        "competitor_count": len(validated.get("competitors", [])),
    })


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
