from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
import auth_routes
import evaluation_routes
from database import init_db

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Optional
from collections import defaultdict
import aiofiles
import asyncio
import json
import logging
import math
import os
import threading
import time
import uuid

logger = logging.getLogger("uvicorn.error")

from file_parser import parse_uploaded_file, build_project_context
from judges import run_all_judges
from gemini_service import (
    verify_environment,
    GeminiQuotaExceededError,
    GeminiPermissionError,
    GeminiServiceUnavailableError,
    ModelResponseError,
    is_quota_error,
    is_daily_quota_error,
    is_permission_error,
    is_service_unavailable_error,
    extract_retry_delay,
    _sanitize_log_message,
    get_configured_model_name,
    get_daily_quota_guidance,
    get_transient_rate_limit_guidance,
    format_retry_delay_human,
    is_daily_quota_exhausted,
)
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
    # Initialize SQLite database schema
    await init_db()
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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],

    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
async def root():
    return {"status": "ok", "message": "IdeaValidator AI is running"}


# Mount authentication and evaluation history routes
app.include_router(auth_routes.router)
app.include_router(evaluation_routes.router)



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
    sync_job_id = None

    _prune_evaluation_jobs()
    with _evaluation_jobs_lock:
        active_running_job = next(
            (job for job in _evaluation_jobs.values()
             if job.get("client_ip") == client_ip and job.get("status") == "running"),
            None
        )
        if active_running_job:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "An evaluation is already running. Please wait for it to complete.",
                    "job_id": active_running_job.get("job_id"),
                    "status": "running",
                },
            )
        sync_job_id = f"eval_sync_{uuid.uuid4().hex[:8]}"
        _evaluation_jobs[sync_job_id] = {
            "job_id": sync_job_id,
            "client_ip": client_ip,
            "status": "running",
            "stage": "Specialist Judges",
            "created_at": time.time(),
        }

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
        eval_start = time.perf_counter()
        try:
            results = await run_all_judges(
                project_context,
                attack_mode=attack_mode,
                external_research=external_research_block,
            )
            logger.info("Total synchronous evaluation pipeline completed in %.2fs.", time.perf_counter() - eval_start)
        except GeminiPermissionError as exc:
            logger.error("AI evaluation permission error (403): %s", exc)
            return JSONResponse(
                status_code=403,
                content={"detail": "Gemini API authentication failed (403 Permission Denied). Please check that GEMINI_API_KEY is valid and has access to the Gemini API."},
            )
        except GeminiQuotaExceededError as exc:
            retry_after = max(1, int(getattr(exc, "retry_after", 10) or 10))
            is_daily = getattr(exc, "is_daily", False)
            model_name = getattr(exc, "model", None) or get_configured_model_name()
            guidance = getattr(exc, "retry_guidance", None) or (
                get_daily_quota_guidance(model_name, retry_after)
                if is_daily
                else get_transient_rate_limit_guidance(model_name, retry_after)
            )
            msg = (
                f"Gemini API daily request quota exceeded for model '{model_name}'. Please wait for the daily quota reset or configure a billing-enabled API key or alternate model. {guidance}"
                if is_daily
                else f"AI evaluation rate limit or quota exceeded for model '{model_name}'. {guidance}"
            )
            category = "daily_quota_exceeded" if is_daily else "quota_exceeded"
            logger.warning("AI evaluation hit Gemini quota limit (model=%s, retry_after=%ds, is_daily=%s): %s", model_name, retry_after, is_daily, exc)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": msg,
                    "category": category,
                    "model": model_name,
                    "retry_after": retry_after,
                    "retry_guidance": guidance,
                },
                headers={"Retry-After": str(retry_after)},
            )
        except GeminiServiceUnavailableError as exc:
            logger.error("AI evaluation provider service unavailable (503): %s", exc)
            return JSONResponse(
                status_code=503,
                content={"detail": "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments."},
            )
        except TimeoutError as exc:
            elapsed = time.perf_counter() - eval_start
            stage = getattr(exc, "judge_name", None) or "AI Judges"
            logger.warning("AI evaluation timed out during stage '%s' after %.2fs: %s", stage, elapsed, exc)
            return JSONResponse(
                status_code=504,
                content={
                    "detail": "AI evaluation timed out. Please try again.",
                    "stage": stage,
                    "elapsed_seconds": round(elapsed, 2),
                },
            )
        except ModelResponseError as exc:
            reason = getattr(exc, "reason", "malformed_json")
            user_msg = {
                "empty_response": "AI judge returned an empty response. Please try again.",
                "blocked": "AI judge response was blocked by safety filters. Please review your submission content.",
                "truncated": "AI judge response was truncated by output length limits. Please try again.",
                "malformed_json": "AI judge returned an unparseable response format. Please try again.",
                "invalid_json_root": "AI judge returned JSON in an invalid format. Please try again.",
                "missing_required_fields": "AI judge response was missing required scoring fields. Please try again.",
                "invalid_field_types": "AI judge response did not match the required scoring schema. Please try again.",
                "invalid_field_values": "AI judge response contained values outside the allowed scoring range. Please try again.",
            }.get(reason, f"AI judge response error ({reason}). Please try again.")
            logger.error("AI evaluation model response error (%s): %s", reason, exc)
            return JSONResponse(
                status_code=502,
                content={"detail": user_msg, "reason": reason},
            )
        except EnvironmentError as exc:
            logger.error("Service configuration unavailable during evaluation: %s", exc, exc_info=True)
            raise HTTPException(status_code=503, detail="Service configuration unavailable.")
        except RuntimeError as exc:
            cause = getattr(exc, "__cause__", None) or exc
            if is_permission_error(cause) or is_permission_error(exc):
                logger.error("AI evaluation permission error wrapped in RuntimeError: %s", exc)
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Gemini API authentication failed (403 Permission Denied). Please check that GEMINI_API_KEY is valid and has access to the Gemini API."},
                )
            if is_quota_error(cause) or is_quota_error(exc):
                q_exc = exc if is_quota_error(exc) else cause
                is_daily = is_daily_quota_error(cause) or is_daily_quota_error(exc)
                model_name = getattr(q_exc, "model", None) or get_configured_model_name()
                delay = int(math.ceil(extract_retry_delay(q_exc)))
                retry_after = max(1, int(getattr(q_exc, "retry_after", delay) or delay))
                guidance = getattr(q_exc, "retry_guidance", None) or (
                    get_daily_quota_guidance(model_name, retry_after)
                    if is_daily
                    else get_transient_rate_limit_guidance(model_name, retry_after)
                )
                msg = (
                    f"Gemini API daily request quota exceeded for model '{model_name}'. Please wait for the daily quota reset or configure a billing-enabled API key or alternate model. {guidance}"
                    if is_daily
                    else f"AI evaluation rate limit or quota exceeded for model '{model_name}'. {guidance}"
                )
                category = "daily_quota_exceeded" if is_daily else "quota_exceeded"
                logger.warning("AI evaluation hit quota error wrapped in RuntimeError (model=%s): %s", model_name, exc)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": msg,
                        "category": category,
                        "model": model_name,
                        "retry_after": retry_after,
                        "retry_guidance": guidance,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            if is_service_unavailable_error(cause) or is_service_unavailable_error(exc):
                logger.error("AI evaluation service unavailable wrapped in RuntimeError: %s", exc)
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments."},
                )
            logger.error("Evaluation service runtime failure: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail="Evaluation service temporarily unavailable.")

        return JSONResponse(content=results)

    finally:
        if sync_job_id:
            with _evaluation_jobs_lock:
                _evaluation_jobs.pop(sync_job_id, None)
        # Always clean up temporary uploaded files, even on exceptions
        cleanup_files(*temp_paths)


# ---------------------------------------------------------------------------
# Background Evaluation Jobs (avoids long-lived HTTP request timeouts)
# ---------------------------------------------------------------------------
_evaluation_jobs = {}
_evaluation_jobs_lock = threading.Lock()
_EVALUATION_JOB_TTL_SECONDS = 3600  # 1 hour
MAX_EVALUATION_JOBS = 500


def _prune_evaluation_jobs() -> None:
    """Prune expired or excess evaluation jobs to prevent memory leaks."""
    now = time.time()
    with _evaluation_jobs_lock:
        stale_keys = [
            k for k, job in list(_evaluation_jobs.items())
            if job.get("status") != "running" and (now - job.get("created_at", now) > _EVALUATION_JOB_TTL_SECONDS)
        ]
        for k in stale_keys:
            _evaluation_jobs.pop(k, None)

        if len(_evaluation_jobs) > MAX_EVALUATION_JOBS:
            completed_keys = [
                k for k, job in list(_evaluation_jobs.items())
                if job.get("status") != "running"
            ]
            completed_keys.sort(key=lambda k: _evaluation_jobs[k].get("created_at", 0))
            to_remove = len(_evaluation_jobs) - MAX_EVALUATION_JOBS
            for k in completed_keys[:to_remove]:
                _evaluation_jobs.pop(k, None)


async def _run_background_evaluation(
    job_id: str,
    project_context: str,
    attack_mode: bool,
    external_research_block: Optional[str],
) -> None:
    with _evaluation_jobs_lock:
        job = _evaluation_jobs.get(job_id)
    if not job:
        return

    eval_start = time.perf_counter()
    logger.info(
        "Background evaluation job '%s' [%s] state=running started",
        job_id,
        job.get("stage", "Specialist Judges"),
    )

    def _update_stage(new_stage: str) -> None:
        with _evaluation_jobs_lock:
            job["stage"] = new_stage
        logger.info(
            "Background evaluation job '%s' [%s] state=running elapsed=%.2fs",
            job_id,
            new_stage,
            round(time.perf_counter() - eval_start, 2),
        )

    try:
        _update_stage("Specialist Judges")
        results = await run_all_judges(
            project_context,
            attack_mode=attack_mode,
            external_research=external_research_block,
            stage_callback=_update_stage,
        )
        duration = round(time.perf_counter() - eval_start, 2)
        with _evaluation_jobs_lock:
            job["status"] = "completed"
            job["stage"] = "Completed"
            job["results"] = results
            job["duration"] = duration
        logger.info(
            "Background evaluation job '%s' [%s] state=completed elapsed=%.2fs",
            job_id,
            "Completed",
            duration,
        )
    except GeminiPermissionError as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = "permission_denied"
            job["error"] = "Gemini API authentication failed (403 Permission Denied). Please check that GEMINI_API_KEY is valid and has access to the Gemini API."
            job["status_code"] = 403
            job["diagnostic"] = "PermissionDenied (403)"
            job["duration"] = duration
        logger.error(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
            job_id,
            job.get("stage", "Unknown"),
            duration,
            type(exc).__name__,
            _sanitize_log_message(str(exc)),
        )
    except GeminiQuotaExceededError as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        is_daily = getattr(exc, "is_daily", False)
        model_name = getattr(exc, "model", None) or get_configured_model_name()
        retry_after = max(1, int(getattr(exc, "retry_after", 10) or 10))
        guidance = getattr(exc, "retry_guidance", None) or (
            get_daily_quota_guidance(model_name, retry_after)
            if is_daily
            else get_transient_rate_limit_guidance(model_name, retry_after)
        )
        category = "daily_quota_exceeded" if is_daily else "quota_exceeded"
        msg = (
            f"Gemini API daily request quota exceeded for model '{model_name}'. Please wait for the daily quota reset or configure a billing-enabled API key or alternate model. {guidance}"
            if is_daily
            else f"AI evaluation rate limit or quota exceeded for model '{model_name}'. {guidance}"
        )
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = category
            job["error"] = msg
            job["model"] = model_name
            job["retry_after"] = retry_after
            job["retry_guidance"] = guidance
            job["status_code"] = 429
            job["diagnostic"] = f"ResourceExhausted (429): model={model_name} " + ("daily quota limit" if is_daily else "rate limit")
            job["duration"] = duration
        logger.warning(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s model=%s: %s",
            job_id,
            job.get("stage", "Unknown"),
            duration,
            type(exc).__name__,
            model_name,
            _sanitize_log_message(str(exc)),
        )
    except GeminiServiceUnavailableError as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = "service_unavailable"
            job["error"] = "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments."
            job["status_code"] = 503
            job["diagnostic"] = "ServiceUnavailable (503)"
            job["duration"] = duration
        logger.error(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
            job_id,
            job.get("stage", "Unknown"),
            duration,
            type(exc).__name__,
            _sanitize_log_message(str(exc)),
        )
    except TimeoutError as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        stage = getattr(exc, "judge_name", None) or job.get("stage", "AI Judges")
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = "timeout"
            job["error"] = f"AI evaluation timed out during stage '{stage}'. Please try again."
            job["stage"] = stage
            job["status_code"] = 504
            job["diagnostic"] = f"TimeoutError (504): stage={stage}"
            job["duration"] = duration
        logger.warning(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
            job_id,
            stage,
            duration,
            type(exc).__name__,
            _sanitize_log_message(str(exc)),
        )
    except ModelResponseError as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        reason = getattr(exc, "reason", "malformed_json")
        user_msg = {
            "empty_response": "AI judge returned an empty response. Please try again.",
            "blocked": "AI judge response was blocked by safety filters. Please review your submission content.",
            "truncated": "AI judge response was truncated by output length limits. Please try again.",
            "malformed_json": "AI judge returned an unparseable response format. Please try again.",
            "invalid_json_root": "AI judge returned JSON in an invalid format. Please try again.",
            "missing_required_fields": "AI judge response was missing required scoring fields. Please try again.",
            "invalid_field_types": "AI judge response did not match the required scoring schema. Please try again.",
            "invalid_field_values": "AI judge response contained values outside the allowed scoring range. Please try again.",
        }.get(reason, f"AI judge response error ({reason}). Please try again.")
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = "malformed_response"
            job["error"] = user_msg
            job["status_code"] = 502
            job["diagnostic"] = f"ModelResponseError (502): reason={reason}"
            job["duration"] = duration
        logger.error(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s reason=%s: %s",
            job_id,
            job.get("stage", "Unknown"),
            duration,
            type(exc).__name__,
            reason,
            _sanitize_log_message(str(exc)),
        )
    except EnvironmentError as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = "environment_error"
            job["error"] = "Service configuration unavailable."
            job["status_code"] = 503
            job["diagnostic"] = "EnvironmentError (503)"
            job["duration"] = duration
        logger.error(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
            job_id,
            job.get("stage", "Unknown"),
            duration,
            type(exc).__name__,
            _sanitize_log_message(str(exc)),
        )
    except asyncio.CancelledError:
        duration = round(time.perf_counter() - eval_start, 2)
        with _evaluation_jobs_lock:
            job["status"] = "failed"
            job["category"] = "cancelled"
            job["stage"] = "Cancelled"
            job["error"] = "Evaluation was cancelled."
            job["status_code"] = 499
            job["diagnostic"] = "CancelledError"
            job["duration"] = duration
        logger.warning(
            "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=CancelledError",
            job_id,
            "Cancelled",
            duration,
        )
        raise
    except Exception as exc:
        duration = round(time.perf_counter() - eval_start, 2)
        cause = getattr(exc, "__cause__", None) or exc
        if is_permission_error(cause) or is_permission_error(exc):
            with _evaluation_jobs_lock:
                job["status"] = "failed"
                job["category"] = "permission_denied"
                job["error"] = "Gemini API authentication failed (403 Permission Denied). Please check that GEMINI_API_KEY is valid and has access to the Gemini API."
                job["status_code"] = 403
                job["diagnostic"] = "PermissionDenied (403)"
                job["duration"] = duration
            logger.error(
                "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
                job_id,
                job.get("stage", "Unknown"),
                duration,
                type(exc).__name__,
                _sanitize_log_message(str(exc)),
            )
        elif is_quota_error(cause) or is_quota_error(exc):
            q_exc = exc if is_quota_error(exc) else cause
            is_daily = is_daily_quota_error(cause) or is_daily_quota_error(exc)
            model_name = getattr(q_exc, "model", None) or get_configured_model_name()
            delay = int(math.ceil(extract_retry_delay(q_exc)))
            retry_after = max(1, int(getattr(q_exc, "retry_after", delay) or delay))
            guidance = getattr(q_exc, "retry_guidance", None) or (
                get_daily_quota_guidance(model_name, retry_after)
                if is_daily
                else get_transient_rate_limit_guidance(model_name, retry_after)
            )
            category = "daily_quota_exceeded" if is_daily else "quota_exceeded"
            msg = (
                f"Gemini API daily request quota exceeded for model '{model_name}'. Please wait for the daily quota reset or configure a billing-enabled API key or alternate model. {guidance}"
                if is_daily
                else f"AI evaluation rate limit or quota exceeded for model '{model_name}'. {guidance}"
            )
            with _evaluation_jobs_lock:
                job["status"] = "failed"
                job["category"] = category
                job["error"] = msg
                job["model"] = model_name
                job["retry_after"] = retry_after
                job["retry_guidance"] = guidance
                job["status_code"] = 429
                job["diagnostic"] = f"ResourceExhausted (429): model={model_name} " + ("daily quota limit" if is_daily else "rate limit")
                job["duration"] = duration
            logger.warning(
                "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s model=%s: %s",
                job_id,
                job.get("stage", "Unknown"),
                duration,
                type(exc).__name__,
                model_name,
                _sanitize_log_message(str(exc)),
            )
        elif is_service_unavailable_error(cause) or is_service_unavailable_error(exc):
            with _evaluation_jobs_lock:
                job["status"] = "failed"
                job["category"] = "service_unavailable"
                job["error"] = "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments."
                job["status_code"] = 503
                job["diagnostic"] = "ServiceUnavailable (503)"
                job["duration"] = duration
            logger.error(
                "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
                job_id,
                job.get("stage", "Unknown"),
                duration,
                type(exc).__name__,
                _sanitize_log_message(str(exc)),
            )
        elif isinstance(cause, TimeoutError) or isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            with _evaluation_jobs_lock:
                job["status"] = "failed"
                job["category"] = "timeout"
                job["error"] = str(exc) if "timed out" in str(exc).lower() else "Evaluation timed out waiting for AI response."
                job["status_code"] = 504
                job["diagnostic"] = "TimeoutError (504)"
                job["duration"] = duration
            logger.warning(
                "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s category=timeout: %s",
                job_id,
                job.get("stage", "Unknown"),
                duration,
                type(exc).__name__,
                _sanitize_log_message(str(exc)),
            )
        else:
            with _evaluation_jobs_lock:
                job["status"] = "failed"
                job["category"] = "service_error"
                job["error"] = "Evaluation service temporarily unavailable."
                job["status_code"] = 502
                job["diagnostic"] = f"{type(exc).__name__} (502)"
                job["duration"] = duration
            logger.error(
                "Background evaluation job '%s' [%s] state=failed elapsed=%.2fs exc_type=%s: %s",
                job_id,
                job.get("stage", "Unknown"),
                duration,
                type(exc).__name__,
                _sanitize_log_message(str(exc)),
            )


@app.post("/evaluate/async")
@app.post("/evaluate/request")
async def create_async_evaluation(
    request: Request,
    pitch_deck: Optional[UploadFile] = File(None),
    readme: Optional[UploadFile] = File(None),
    attack_mode: bool = Form(False),
    research_request_id: Optional[str] = Form(None),
):
    """
    Start an asynchronous AI evaluation job.
    Returns 202 Accepted with a job_id for polling GET /evaluate/status/{job_id}.
    Avoids long HTTP request timeouts on reverse proxies.
    """
    client_ip = get_client_ip(request)
    allowed, retry_after = check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded: maximum 5 evaluations per minute."},
            headers={"Retry-After": str(retry_after)},
        )

    if not pitch_deck and not readme:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one file: a Pitch Deck (PDF/PPTX) or a README.md file.",
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

        external_research_block = None
        if research_request_id and research_request_id.strip():
            imported = research_module.get_imported_research(
                research_request_id.strip(), project_context
            )
            if imported:
                external_research_block = research_module.format_research_for_prompt(imported)

        _prune_evaluation_jobs()
        with _evaluation_jobs_lock:
            # Prevent duplicate submissions while an evaluation is already running for this client IP
            active_running_job = next(
                (job for job in _evaluation_jobs.values()
                 if job.get("client_ip") == client_ip and job.get("status") == "running"),
                None
            )
            if active_running_job:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "An evaluation is already running. Please wait for it to complete.",
                        "job_id": active_running_job.get("job_id"),
                        "status": "running",
                    },
                )

            job_id = f"eval_{uuid.uuid4().hex[:12]}"
            _evaluation_jobs[job_id] = {
                "job_id": job_id,
                "client_ip": client_ip,
                "status": "running",
                "stage": "Specialist Judges",
                "created_at": time.time(),
                "results": None,
                "error": None,
                "status_code": None,
                "duration": None,
            }

        task = asyncio.create_task(
            _run_background_evaluation(
                job_id,
                project_context,
                attack_mode,
                external_research_block,
            )
        )
        with _evaluation_jobs_lock:
            if job_id in _evaluation_jobs:
                _evaluation_jobs[job_id]["task"] = task

        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "running",
                "stage": "Specialist Judges",
                "message": "Evaluation started in background.",
            },
        )
    finally:
        cleanup_files(*temp_paths)


@app.post("/evaluate/cancel/{job_id}")
async def cancel_evaluation(job_id: str):
    """Cancel an in-flight background evaluation job."""
    with _evaluation_jobs_lock:
        job = _evaluation_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Evaluation job not found or expired.")
        if job.get("status") != "running":
            return {"status": job.get("status"), "message": f"Job is already {job.get('status')}."}
        task = job.get("task")
        job["status"] = "failed"
        job["category"] = "cancelled"
        job["stage"] = "Cancelled"
        job["error"] = "Evaluation was cancelled."
        job["status_code"] = 499
        job["diagnostic"] = "CancelledError"
    if task and not task.done():
        task.cancel()
    return {"status": "cancelled", "job_id": job_id}


@app.get("/evaluate/status/{job_id}")
async def get_evaluation_status(job_id: str):
    """
    Check the status of an asynchronous evaluation job.
    Returns 200 with consistent JSON for running, completed, or failed jobs.
    Returns 404 for unknown or expired job IDs.
    """
    _prune_evaluation_jobs()
    with _evaluation_jobs_lock:
        job = _evaluation_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Evaluation job not found or expired.")
        job_copy = dict(job)

    created_at = job_copy.get("created_at", time.time())
    elapsed = round(time.time() - created_at, 1)
    status = job_copy.get("status", "running")
    stage = job_copy.get("stage", "Specialist Judges")

    logger.info(
        "Diagnostic poll job '%s' [%s] state=%s elapsed=%.1fs",
        job_id,
        stage,
        status,
        elapsed,
    )

    if status == "completed":
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "status": "completed",
                "stage": stage,
                "results": job_copy.get("results"),
                "duration_seconds": job_copy.get("duration", elapsed),
                "elapsed_seconds": elapsed,
            },
        )
    elif status == "failed":
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "status": "failed",
                "category": job_copy.get("category", "service_error"),
                "stage": stage,
                "detail": job_copy.get("error", "Evaluation service temporarily unavailable."),
                "error": job_copy.get("error", "Evaluation service temporarily unavailable."),
                "error_code": job_copy.get("status_code", 500),
                "model": job_copy.get("model"),
                "retry_after": job_copy.get("retry_after"),
                "retry_guidance": job_copy.get("retry_guidance"),
                "diagnostic": job_copy.get("diagnostic", ""),
                "duration_seconds": job_copy.get("duration", elapsed),
                "elapsed_seconds": elapsed,
            },
        )
    else:
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "status": "running",
                "stage": stage,
                "elapsed_seconds": elapsed,
            },
        )


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

    # Import via the public research module API.
    # Idea-binding is enforced later by get_imported_research() at /evaluate time,
    # since the import endpoint cannot reconstruct the original project_context
    # from its one-way hash.
    try:
        validated = research_module.import_research_by_token(
            request_id, raw_token, payload
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg or "expired" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "capability token" in msg.lower():
            raise HTTPException(status_code=401, detail=msg)
        if "already been imported" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)

    return JSONResponse(content={
        "status": "imported",
        "request_id": request_id,
        "competitor_count": len(validated.get("competitors", [])),
    })


@app.post("/research/auto")
async def start_automated_research(
    request: Request,
    pitch_deck: Optional[UploadFile] = File(None),
    readme: Optional[UploadFile] = File(None),
):
    """
    Start automated market and competitor research via Agent37 Mythos in the background.
    Never exposes auth tokens or Agent37 API keys in the response.
    Returns 202 with request_id for polling status via GET /research/status/{request_id}.
    """
    client_ip = get_client_ip(request)
    allowed, retry_after = check_rate_limit(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please wait before requesting automated research."},
            headers={"Retry-After": str(retry_after)},
        )

    if not pitch_deck and not readme:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one file to start automated research.",
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

        request_id = req["request_id"]
        auth_token = req["auth_token"]
        idea_summary = project_context[:1500]
        research_prompt = research_module.build_mythos_research_prompt(request_id, idea_summary)

        # Store research prompt for fallback and mark as processing
        research_module.set_research_prompt(request_id, research_prompt)
        research_module.set_auto_status(request_id, "processing")

        # Spawn asynchronous background task
        async def _background_research():
            try:
                await research_module.run_agent37_research(
                    request_id=request_id,
                    auth_token=auth_token,
                    project_context=project_context,
                    idea_summary=idea_summary,
                )
                research_module.set_auto_status(request_id, "completed")
            except (research_module.Agent37Error, ValueError) as exc:
                logger.warning("Automated Agent37 research failed for request %s: %s", request_id, exc)
                research_module.set_auto_status(request_id, "failed", str(exc))
            except Exception as exc:
                logger.error("Unexpected error during Agent37 automated research: %s", exc, exc_info=False)
                research_module.set_auto_status(request_id, "failed", "An unexpected error occurred during research.")

        asyncio.create_task(_background_research())

        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "request_id": request_id,
                "expires_in": req["expires_in"],
                "research_prompt": research_prompt,
            },
        )

    finally:
        cleanup_files(*temp_paths)


@app.get("/research/status/{request_id}")
async def get_research_status(request_id: str):
    """
    Poll the status of an automated Agent37 research request.
    Returns status ('processing', 'completed', 'failed') and competitor count when done.
    Never exposes internal auth tokens or API keys.
    """
    status_info = research_module.get_auto_status(request_id)
    if status_info is None:
        raise HTTPException(status_code=404, detail="Research request not found or has expired.")

    prompt = research_module.get_research_prompt(request_id)
    res = dict(status_info)
    if prompt:
        res["research_prompt"] = prompt
    return JSONResponse(content=res)


@app.exception_handler(GeminiPermissionError)
async def gemini_permission_exception_handler(request: Request, exc: GeminiPermissionError):
    """Map Gemini authentication failure to clean HTTP 403 response."""
    return JSONResponse(
        status_code=403,
        content={"detail": "Gemini API authentication failed (403 Permission Denied). Please check that GEMINI_API_KEY is valid and has access to the Gemini API."},
    )


@app.exception_handler(GeminiServiceUnavailableError)
async def gemini_service_unavailable_exception_handler(request: Request, exc: GeminiServiceUnavailableError):
    """Map Gemini 503 unavailable to clean HTTP 503 response."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments."},
    )


@app.exception_handler(GeminiQuotaExceededError)
async def gemini_quota_exception_handler(request: Request, exc: GeminiQuotaExceededError):
    """Map Gemini quota exhaustion to clean HTTP 429 response without leaking details."""
    retry_after = max(1, int(getattr(exc, "retry_after", 10) or 10))
    is_daily = getattr(exc, "is_daily", False)
    model_name = getattr(exc, "model", None) or get_configured_model_name()
    guidance = getattr(exc, "retry_guidance", None) or (
        get_daily_quota_guidance(model_name, retry_after)
        if is_daily
        else get_transient_rate_limit_guidance(model_name, retry_after)
    )
    category = "daily_quota_exceeded" if is_daily else "quota_exceeded"
    msg = (
        f"Gemini API daily request quota exceeded for model '{model_name}'. Please wait for the daily quota reset or configure a billing-enabled API key or alternate model. {guidance}"
        if is_daily
        else f"AI evaluation rate limit or quota exceeded for model '{model_name}'. {guidance}"
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": msg,
            "category": category,
            "model": model_name,
            "retry_after": retry_after,
            "retry_guidance": guidance,
        },
        headers={"Retry-After": str(retry_after)},
    )


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
