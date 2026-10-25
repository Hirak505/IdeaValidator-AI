import google.generativeai as genai
import json
import logging
import math
import os
import random
import re
import asyncio
import threading
import time
from functools import partial
from typing import Optional, Any
from dotenv import load_dotenv

try:
    from google.api_core.exceptions import (
        DeadlineExceeded,
        ResourceExhausted,
        TooManyRequests,
        PermissionDenied,
        Forbidden,
        ServiceUnavailable,
        InternalServerError,
    )
except ImportError:
    DeadlineExceeded = None
    ResourceExhausted = None
    TooManyRequests = None
    PermissionDenied = None
    Forbidden = None
    ServiceUnavailable = None
    InternalServerError = None

from pathlib import Path as _Path
load_dotenv(_Path(__file__).resolve().parent / ".env")

logger = logging.getLogger("uvicorn.error")

_configured = False
DEFAULT_TIMEOUT_SECONDS = 180.0
MIN_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 300.0
SDK_TIMEOUT_GRACE_SECONDS = 5.0


def _get_timeout_seconds() -> float:
    raw_timeout = os.getenv("GEMINI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout_seconds = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"GEMINI_TIMEOUT_SECONDS must be a number between "
            f"{MIN_TIMEOUT_SECONDS:g} and {MAX_TIMEOUT_SECONDS:g} seconds."
        ) from exc
    if not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise RuntimeError(
            f"GEMINI_TIMEOUT_SECONDS must be between "
            f"{MIN_TIMEOUT_SECONDS:g} and {MAX_TIMEOUT_SECONDS:g} seconds."
        )
    return timeout_seconds


TIMEOUT_SECONDS = _get_timeout_seconds()


def _get_sdk_timeout_seconds() -> float:
    return max(1.0, TIMEOUT_SECONDS - SDK_TIMEOUT_GRACE_SECONDS)


class GeminiQuotaExceededError(RuntimeError):
    """Raised when Gemini API quota or rate limits are exceeded and retries are exhausted."""
    def __init__(
        self,
        message: str = "Gemini API rate limit or quota exceeded. Please wait and try again.",
        retry_after: int | float = 10,
        is_daily: bool = False,
        model: Optional[str] = None,
        retry_guidance: Optional[str] = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.is_daily = is_daily
        self.model = model
        self.retry_guidance = retry_guidance


class GeminiPermissionError(RuntimeError):
    """Raised on Gemini API permission denied or invalid credentials (HTTP 403). Non-retryable."""
    def __init__(
        self,
        message: str = "Gemini API authentication failed (403 Permission Denied). Please check that GEMINI_API_KEY is valid and has access to the Gemini API.",
    ):
        super().__init__(message)
        self.status_code = 403


class GeminiServiceUnavailableError(RuntimeError):
    """Raised when Gemini API returns 503 Service Unavailable and retries are exhausted."""
    def __init__(
        self,
        message: str = "Gemini AI service is temporarily unavailable (503 Service Unavailable). Please try again in a few moments.",
        retry_after: int | float = 5,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.status_code = 503


def is_quota_error(exc: Exception) -> bool:
    """Detect if an exception represents a 429 / ResourceExhausted / quota exceeded error."""
    if exc is None:
        return False
    if ResourceExhausted and isinstance(exc, ResourceExhausted):
        return True
    if TooManyRequests and isinstance(exc, TooManyRequests):
        return True
    cls_name = type(exc).__name__
    if cls_name in ("ResourceExhausted", "TooManyRequests", "MockResourceExhausted", "GeminiQuotaExceededError"):
        return True
    code = getattr(exc, "code", None)
    if code in (429, 8):  # 8 is gRPC StatusCode.RESOURCE_EXHAUSTED
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    grpc_code = getattr(exc, "grpc_status_code", None)
    if grpc_code in (8, 429):
        return True
    msg = str(exc).lower()
    if "resource_exhausted" in msg or "resourceexhausted" in msg:
        return True
    if "429" in msg and any(kw in msg for kw in ("quota", "rate limit", "exceeded", "too many requests", "retry in")):
        return True
    if "quota exceeded" in msg:
        return True
    return False


def extract_provider_retry_delay(exc: Exception) -> float | None:
    """
    Extract the exact retry delay requested by the provider, if present.
    Returns the requested delay in seconds (float), or None if the provider did not specify a delay.
    """
    if exc is None:
        return None

    # 1. Direct attributes on exception
    for attr in ("retry_delay", "retry_after"):
        val = getattr(exc, attr, None)
        if val is not None:
            if hasattr(val, "total_seconds"):
                return float(val.total_seconds())
            elif hasattr(val, "seconds"):
                return float(val.seconds) + float(getattr(val, "nanos", 0)) / 1e9
            elif isinstance(val, (int, float)):
                return float(val)

    # 2. Check protobuf error_details or metadata if present
    if hasattr(exc, "error_details") and exc.error_details:
        try:
            for detail in exc.error_details:
                # e.g., google.rpc.error_details_pb2.RetryInfo
                retry_delay = getattr(detail, "retry_delay", None)
                if retry_delay is not None:
                    if hasattr(retry_delay, "total_seconds"):
                        return float(retry_delay.total_seconds())
                    elif hasattr(retry_delay, "seconds"):
                        return float(retry_delay.seconds) + float(getattr(retry_delay, "nanos", 0)) / 1e9
        except Exception:
            pass

    if hasattr(exc, "metadata") and exc.metadata:
        try:
            for item in exc.metadata:
                if isinstance(item, (tuple, list)) and len(item) == 2:
                    k, v = str(item[0]).lower(), str(item[1])
                    if "retry" in k:
                        m = re.search(r"(\d+(?:\.\d+)?)", v)
                        if m:
                            return float(m.group(1))
        except Exception:
            pass

    exc_str = str(exc)

    # 3. Protobuf text format: retry_delay { seconds: 51 nanos: 415000000 }
    m = re.search(r"retry_delay\s*\{[^}]*?seconds:\s*([0-9]+)(?:[^}]*?nanos:\s*([0-9]+))?", exc_str, re.IGNORECASE | re.DOTALL)
    if m:
        try:
            secs = float(m.group(1))
            nanos = float(m.group(2) or 0) / 1e9
            return secs + nanos
        except ValueError:
            pass

    # 4. "Please retry in 51.415001046s" or "Please retry in 51s"
    m = re.search(r"(?:please\s+)?retry\s+in\s+([0-9]+(?:\.[0-9]+)?)\s*s\b", exc_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    # 5. "(seconds: 49940)"
    m = re.search(r"\(seconds:\s*([0-9]+(?:\.[0-9]+)?)\)", exc_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    # 6. "retry[-_]after[:=\s]+([0-9]+(?:\.[0-9]+)?)"
    m = re.search(r"retry[-_]after[:=\s]+([0-9]+(?:\.[0-9]+)?)", exc_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    # 7. "retry in 13h52m20s"
    m = re.search(r"retry\s+in\s+(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s)?", exc_str, re.IGNORECASE)
    if m and any(m.groups()):
        try:
            h = float(m.group(1) or 0)
            mins = float(m.group(2) or 0)
            s = float(m.group(3) or 0)
            total = h * 3600 + mins * 60 + s
            if total > 0:
                return total
        except ValueError:
            pass

    return None


def is_daily_quota_error(exc: Exception) -> bool:
    """Detect if a 429 error represents an unretryable daily quota exhaustion (not transient RPM rate limit)."""
    if exc is None:
        return False
    if getattr(exc, "is_daily", False):
        return True
    msg = str(exc).lower()

    # Explicit per-minute limits or short retry intervals are transient rate limits, not daily quota exhaustion
    has_rpm_metric = any(rpm in msg for rpm in ("perminute", "per_minute", "requests_per_minute", "generaterequestsperminute"))

    # Explicit daily metric keywords
    has_daily_metric = any(metric in msg for metric in (
        "perday",
        "per_day",
        "requests_per_day",
        "daily",
        "generaterequestsperday",
        "requests per day",
        "quota exceeded per day",
        "daily quota exceeded",
        "daily request limit",
    ))
    if has_daily_metric:
        return True

    # Free-tier daily limit (e.g. limit: 20 for free tier requests without RPM metric)
    if ("free_tier" in msg or "free tier" in msg or "generativelanguage" in msg) and re.search(r"limit:\s*20\b", msg):
        if not has_rpm_metric:
            return True

    # Retry delay in hours represents daily window reset
    if re.search(r"retry\s+in\s+([0-9]+)\s*h", msg):
        return True

    # Provider delay > 120s indicates daily quota window (transient RPM windows are <= 60s)
    provider_delay = extract_provider_retry_delay(exc)
    if provider_delay is not None and provider_delay > 120:
        return True

    return False


def is_permission_error(exc: Exception) -> bool:
    """Detect if an exception represents a 403 / PermissionDenied / Invalid API Key error."""
    if exc is None:
        return False
    if PermissionDenied and isinstance(exc, PermissionDenied):
        return True
    if Forbidden and isinstance(exc, Forbidden):
        return True
    cls_name = type(exc).__name__
    if cls_name in ("PermissionDenied", "Forbidden", "GeminiPermissionError", "MockPermissionDenied"):
        return True
    code = getattr(exc, "code", None)
    if code in (403, 7):  # 7 is gRPC StatusCode.PERMISSION_DENIED
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code == 403:
        return True
    grpc_code = getattr(exc, "grpc_status_code", None)
    if grpc_code in (7, 403):
        return True
    msg = str(exc).lower()
    if "permission_denied" in msg or "permissiondenied" in msg:
        return True
    if "403" in msg and any(kw in msg for kw in ("permission", "denied", "forbidden", "unauthorized", "api_key", "key")):
        return True
    if "api key not valid" in msg or "api_key_invalid" in msg or "caller does not have permission" in msg:
        return True
    return False


def is_service_unavailable_error(exc: Exception) -> bool:
    """Detect if an exception represents a 503 / ServiceUnavailable error."""
    if exc is None:
        return False
    if ServiceUnavailable and isinstance(exc, ServiceUnavailable):
        return True
    cls_name = type(exc).__name__
    if cls_name in ("ServiceUnavailable", "GeminiServiceUnavailableError", "MockServiceUnavailable"):
        return True
    code = getattr(exc, "code", None)
    if code in (503, 14):  # 14 is gRPC StatusCode.UNAVAILABLE
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code == 503:
        return True
    grpc_code = getattr(exc, "grpc_status_code", None)
    if grpc_code in (14, 503):
        return True
    msg = str(exc).lower()
    if "service_unavailable" in msg or "serviceunavailable" in msg:
        return True
    if "503" in msg and any(kw in msg for kw in ("service", "unavailable", "temporarily", "overloaded", "server")):
        return True
    return False


def extract_retry_delay(
    exc: Exception,
    attempt: int = 0,
    initial_delay: float = 2.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
) -> float:
    """
    Extract retry delay suggested by provider, or calculate exponential backoff with jitter.
    Guarantees that if the provider specified a delay, the returned delay is NEVER less than
    the provider's requested delay (never retries early).
    """
    provider_delay = extract_provider_retry_delay(exc)
    jitter = random.uniform(0.1, 0.4)

    if provider_delay is not None and provider_delay > 0:
        # Never retry earlier than the provider-requested delay: add positive jitter
        return provider_delay + jitter

    # Fallback to exponential backoff with jitter, bounded by max_delay
    backoff = (initial_delay * (backoff_factor ** attempt))
    final_delay = backoff + jitter
    return max(0.5, min(final_delay, max_delay))


def _sanitize_log_message(msg: str) -> str:
    """Scrub sensitive API keys, tokens, or credentials from log strings."""
    if not isinstance(msg, str):
        msg = str(msg)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key and len(api_key) > 6:
        msg = msg.replace(api_key, "[REDACTED_API_KEY]")
    # Redact common key=value patterns in URLs or query strings
    msg = re.sub(r"(?i)(key|token|secret|password|api_key)=([A-Za-z0-9_\-\.]+)", r"\1=[REDACTED]", msg)
    return msg


def verify_environment() -> None:
    """
    Refuse to start if required environment variables are missing or placeholders.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FATAL: GEMINI_API_KEY environment variable is not set in .env")
    if api_key in ("<your_gemini_api_key_here>", "your_gemini_api_key_here", "your_actual_key_here"):
        raise RuntimeError("FATAL: GEMINI_API_KEY is still set to placeholder value in .env")


def _configure_gemini():
    global _configured
    if not _configured:
        verify_environment()
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        genai.configure(api_key=api_key)
        _configured = True


def get_configured_model_name() -> str:
    """Return the currently configured Gemini model name from environment variables."""
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"


def format_retry_delay_human(seconds: float | int | None) -> str:
    """Format seconds into a human-readable duration (e.g., '13h 52m', '45s')."""
    if seconds is None or seconds <= 0:
        return "momentarily"
    sec = int(round(seconds))
    if sec < 60:
        return f"{sec}s"
    mins = sec // 60
    rem_sec = sec % 60
    if mins < 60:
        return f"{mins}m {rem_sec}s" if rem_sec else f"{mins}m"
    hours = mins // 60
    rem_mins = mins % 60
    return f"{hours}h {rem_mins}m" if rem_mins else f"{hours}h"


def get_daily_quota_guidance(model_name: str, retry_after: float | int = 86400) -> str:
    """Provide clear, actionable guidance when daily request quota is exhausted."""
    duration_str = format_retry_delay_human(retry_after)
    return (
        f"Daily request quota is exhausted for model '{model_name}'. "
        f"Quota will reset in ~{duration_str}. To resume immediately, "
        f"switch to another supported model by setting GEMINI_MODEL in backend/.env "
        f"(e.g., gemini-1.5-flash, gemini-2.0-flash, or gemini-2.5-flash), "
        f"or upgrade your Google AI Studio project to a billing-enabled tier."
    )


def get_transient_rate_limit_guidance(model_name: str, retry_after: float | int = 10) -> str:
    """Provide clear guidance for transient per-minute (RPM) rate limits."""
    duration_str = format_retry_delay_human(retry_after)
    return (
        f"Per-minute rate limit (RPM) temporarily reached for model '{model_name}'. "
        f"Please wait {duration_str} before retrying."
    )


_daily_quota_lock = threading.Lock()
_daily_quota_exhausted_models: dict[str, dict] = {}


def mark_daily_quota_exhausted(
    model_name: Optional[str] = None,
    retry_after: float | int = 86400,
    message: str = "",
) -> None:
    """Record that the specified Gemini model has exhausted its daily request quota."""
    name = (model_name or get_configured_model_name()).strip()
    retry_secs = max(1.0, float(retry_after or 86400))
    now = time.time()
    reset_at = now + retry_secs
    with _daily_quota_lock:
        _daily_quota_exhausted_models[name] = {
            "model": name,
            "exhausted_at": now,
            "reset_at": reset_at,
            "retry_after": retry_secs,
            "message": message,
        }
    logger.warning(
        "Daily quota exhaustion recorded for model '%s' (retry_after=%.1fs, resets in %s).",
        name,
        retry_secs,
        format_retry_delay_human(retry_secs),
    )


def is_daily_quota_exhausted(model_name: Optional[str] = None) -> bool:
    """Check if the given (or configured) model's daily quota is currently marked as exhausted."""
    name = (model_name or get_configured_model_name()).strip()
    now = time.time()
    with _daily_quota_lock:
        info = _daily_quota_exhausted_models.get(name)
        if not info:
            return False
        if now >= info["reset_at"]:
            del _daily_quota_exhausted_models[name]
            return False
        return True


def get_daily_quota_info(model_name: Optional[str] = None) -> Optional[dict]:
    """Retrieve details on daily quota exhaustion for the specified model, or None if not exhausted."""
    name = (model_name or get_configured_model_name()).strip()
    now = time.time()
    with _daily_quota_lock:
        info = _daily_quota_exhausted_models.get(name)
        if not info:
            return None
        if now >= info["reset_at"]:
            del _daily_quota_exhausted_models[name]
            return None
        remaining = max(1.0, info["reset_at"] - now)
        return {
            "model": name,
            "exhausted_at": info["exhausted_at"],
            "reset_at": info["reset_at"],
            "retry_after": remaining,
            "guidance": get_daily_quota_guidance(name, remaining),
            "message": info["message"],
        }


def clear_daily_quota_exhaustion(model_name: Optional[str] = None) -> None:
    """Clear recorded daily quota exhaustion state (for all models if model_name is None)."""
    with _daily_quota_lock:
        if model_name:
            _daily_quota_exhausted_models.pop(model_name.strip(), None)
        else:
            _daily_quota_exhausted_models.clear()


def get_model():
    _configure_gemini()
    model_name = get_configured_model_name()
    max_output_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=genai.types.GenerationConfig(
            temperature=0.4,
            top_p=0.95,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        ),
    )


class ModelResponseError(ValueError):
    """Raised when a model response cannot be parsed into valid evaluation JSON.

    Attributes:
        reason: human-readable diagnostic category (e.g. "empty_response", "blocked",
                "malformed_json", "missing_required_fields").
        preview: short, sanitized snippet of the raw response (never contains API keys).
        parse_exception: underlying JSONDecodeError or other parsing exception.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = "unknown",
        preview: str = "",
        parse_exception: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.preview = preview
        self.parse_exception = parse_exception


# Required top-level keys for judges
_REQUIRED_SPECIALIST_KEYS = {"score", "strengths", "weaknesses", "comments"}
_REQUIRED_CHIEF_KEYS = {"overall_score", "final_verdict", "top_strengths", "top_improvements"}
_REQUIRED_JUDGE_KEYS = _REQUIRED_SPECIALIST_KEYS


def _clean_trailing_commas(s: str) -> str:
    """Safely strip trailing commas before closing braces or brackets."""
    return re.sub(r",\s*([\]}])", r"\1", s)


def _try_parse_candidate(candidate_str: str) -> tuple[Optional[dict], Optional[Exception]]:
    """Attempt to parse candidate_str with strict=False and trailing-comma resilience."""
    candidate_str = candidate_str.strip()
    if not candidate_str:
        return None, None
    last_err = None
    try:
        val = json.loads(candidate_str, strict=False)
        return val, None
    except (json.JSONDecodeError, TypeError) as exc:
        last_err = exc

    cleaned = _clean_trailing_commas(candidate_str)
    if cleaned != candidate_str:
        try:
            val = json.loads(cleaned, strict=False)
            return val, None
        except (json.JSONDecodeError, TypeError) as exc:
            last_err = exc

    return None, last_err


def _extract_outermost_json_object(text: str) -> str | None:
    """Return the substring of *text* corresponding to the outermost ``{…}`` block
    using brace-depth counting so that nested objects are not truncated.

    Returns ``None`` when no balanced object is found.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            if in_string:
                escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_from_response(text: str, model_name: Optional[str] = None) -> dict:
    """Robustly extract a JSON object from a model response.

    Handles:
    - Direct JSON text
    - JSON inside Markdown ``json`` code fences
    - Leading/trailing explanatory prose surrounding the JSON
    - Surrounding whitespace
    - Unescaped control characters/newlines inside string fields
    - Trailing commas in arrays or objects

    Raises ``ModelResponseError`` with a diagnostic *reason* and sanitized
    preview when no valid JSON object can be recovered.
    """
    if not text or not str(text).strip():
        raise ModelResponseError(
            "Model returned an empty response.",
            reason="empty_response",
            preview="",
        )

    text = str(text).strip()
    safe_preview = _sanitize_log_message(text[:300].replace("\n", " "))
    last_parse_exception = None

    # 1. Try direct parse of the whole text. A valid non-object JSON root is
    #    not a judge result and must not be mined for an inner object.
    parsed_direct, direct_err = _try_parse_candidate(text)
    if isinstance(parsed_direct, dict):
        return parsed_direct
    if parsed_direct is not None and not isinstance(parsed_direct, dict):
        raise ModelResponseError(
            "Model response JSON root must be an object.",
            reason="invalid_json_root",
            preview=safe_preview,
            parse_exception=direct_err,
        )
    if direct_err:
        last_parse_exception = direct_err

    # 2. Check for markdown code fences (e.g. ```json ... ``` or ``` ... ```).
    fence_matches = list(re.finditer(r"```(?:json)?[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```", text, re.IGNORECASE | re.DOTALL))
    if fence_matches:
        dict_candidates = []
        non_dict_candidate = None
        for fm in fence_matches:
            inner = fm.group(1).strip()
            parsed_inner, inner_err = _try_parse_candidate(inner)
            if inner_err:
                last_parse_exception = inner_err
            if isinstance(parsed_inner, dict):
                dict_candidates.append(parsed_inner)
            elif parsed_inner is not None:
                non_dict_candidate = parsed_inner
        if len(dict_candidates) == 1:
            return dict_candidates[0]
        elif len(dict_candidates) > 1:
            raise ModelResponseError(
                "Multiple JSON objects found in fenced model response.",
                reason="malformed_json",
                preview=safe_preview,
                parse_exception=last_parse_exception,
            )
        elif non_dict_candidate is not None:
            raise ModelResponseError(
                "Fenced model response JSON root must be an object.",
                reason="invalid_json_root",
                preview=safe_preview,
                parse_exception=last_parse_exception,
            )

    # 3. Check if whole text is surrounded by JSON array brackets
    if text.startswith("[") and text.endswith("]"):
        raise ModelResponseError(
            "Model response JSON root must be an object.",
            reason="invalid_json_root",
            preview=safe_preview,
            parse_exception=last_parse_exception,
        )

    # 4. Search for top-level JSON objects in prose using JSONDecoder with strict=False
    decoder = json.JSONDecoder(strict=False)
    candidates = []
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            result, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError as exc:
            last_parse_exception = exc
            continue
        if isinstance(result, dict):
            candidates.append((start, end, result))

    top_level_candidates = [
        candidate
        for candidate in candidates
        if not any(
            outer_start < candidate[0] and candidate[1] <= outer_end
            for outer_start, outer_end, _ in candidates
        )
    ]
    if len(top_level_candidates) == 1:
        start, end, result = top_level_candidates[0]
        prefix = text[:start].rstrip()
        suffix = text[end:].lstrip()
        if not prefix.endswith("[") and not suffix.startswith("]"):
            return result
    elif len(top_level_candidates) > 1:
        raise ModelResponseError(
            "Could not parse structured evaluation output.",
            reason="malformed_json",
            preview=safe_preview,
            parse_exception=last_parse_exception,
        )

    # 5. Outermost balanced brace fallback (handles trailing commas inside prose)
    outer = _extract_outermost_json_object(text)
    if outer:
        parsed_outer, outer_err = _try_parse_candidate(outer)
        if outer_err:
            last_parse_exception = outer_err
        if isinstance(parsed_outer, dict):
            start = text.find(outer)
            prefix = text[:start].rstrip()
            suffix = text[start + len(outer):].lstrip()
            if not prefix.endswith("[") and not suffix.startswith("]"):
                return parsed_outer

    # Nothing worked — raise ModelResponseError with diagnostic preview and last parsing exception
    err = ModelResponseError(
        "Could not parse structured evaluation output.",
        reason="malformed_json",
        preview=safe_preview,
        parse_exception=last_parse_exception,
    )
    if last_parse_exception:
        err.__cause__ = last_parse_exception
    raise err


def _unwrap_nested_dict(data: dict) -> dict:
    """If *data* wraps the judge payload in a single top-level dictionary, unwrap it."""
    if not isinstance(data, dict):
        return data
    if len(data) == 1:
        val = next(iter(data.values()))
        if isinstance(val, dict):
            judge_markers = {"score", "overall_score", "strengths", "top_strengths", "final_verdict", "comments"}
            if any(k in val for k in judge_markers):
                return val
    for wrapper_key in ("chief_judge", "evaluation", "report", "result", "judge_report"):
        if wrapper_key in data and isinstance(data[wrapper_key], dict):
            val = data[wrapper_key]
            judge_markers = {"score", "overall_score", "strengths", "top_strengths", "final_verdict", "comments"}
            if any(k in val for k in judge_markers):
                return val
    return data


def _normalize_alternative_fields(data: dict, is_chief: bool) -> dict:
    """Normalize alternative field names unambiguously without fabricating missing values."""
    if not isinstance(data, dict):
        return data

    # 1. Score normalization
    if data.get("overall_score") is None and data.get("score") is not None:
        data["overall_score"] = data["score"]
    elif data.get("score") is None and data.get("overall_score") is not None:
        data["score"] = data["overall_score"]

    # 2. Verdict / Comments normalization
    if data.get("final_verdict") is None:
        for alt in ("verdict", "comments", "summary"):
            if data.get(alt) is not None:
                data["final_verdict"] = data[alt]
                break
    if data.get("comments") is None:
        for alt in ("final_verdict", "verdict", "summary"):
            if data.get(alt) is not None:
                data["comments"] = data[alt]
                break

    # 3. Strengths normalization
    if data.get("top_strengths") is None:
        for alt in ("strengths", "key_strengths"):
            if data.get(alt) is not None:
                data["top_strengths"] = data[alt]
                break
    if data.get("strengths") is None:
        for alt in ("top_strengths", "key_strengths"):
            if data.get(alt) is not None:
                data["strengths"] = data[alt]
                break

    # 4. Improvements / Weaknesses normalization
    if data.get("top_improvements") is None:
        for alt in ("weaknesses", "improvements", "key_improvements", "areas_for_improvement"):
            if data.get(alt) is not None:
                data["top_improvements"] = data[alt]
                break
    if data.get("weaknesses") is None:
        for alt in ("top_improvements", "improvements", "key_improvements", "areas_for_improvement"):
            if data.get(alt) is not None:
                data["weaknesses"] = data[alt]
                break

    return data


def validate_judge_schema(data: dict, judge_name: str) -> dict:
    """Verify that *data* contains the required keys and types for the specified judge.

    Handles unambiguous unwrapping of nested payloads and field name normalization.
    Does **not** invent missing scores or fabricate fields — raises
    ``ModelResponseError`` if required keys are absent or have incorrect types.
    """
    if not isinstance(data, dict):
        raise ModelResponseError(
            f"{judge_name} response is not a JSON object (got {type(data).__name__}).",
            reason="invalid_field_types",
            preview=str(data)[:200],
        )

    # 1. Unwrap nested dictionary if present
    data = _unwrap_nested_dict(data)

    is_chief = "chief" in judge_name.lower()

    # 2. Normalize alternative field names
    data = _normalize_alternative_fields(data, is_chief)

    # 3. Check for missing required keys
    required_keys = _REQUIRED_CHIEF_KEYS if is_chief else _REQUIRED_SPECIALIST_KEYS
    missing = required_keys - set(data.keys())
    if missing:
        logger.warning(
            "Judge '%s' schema validation failed — missing: %s, available keys: %s",
            judge_name,
            sorted(missing),
            list(data.keys()),
        )
        raise ModelResponseError(
            f"{judge_name} response missing required fields: {', '.join(sorted(missing))}",
            reason="missing_required_fields",
            preview=str(data)[:200],
        )

    # 4. Validate field types without fabricating values
    if is_chief:
        # Score type check
        score_val = data.get("overall_score")
        if isinstance(score_val, bool) or score_val is None:
            raise ModelResponseError(
                f"{judge_name} has invalid overall_score type: expected number, got {type(score_val).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if isinstance(score_val, str):
            try:
                data["overall_score"] = float(score_val)
            except ValueError:
                raise ModelResponseError(
                    f"{judge_name} has invalid overall_score type: cannot parse '{score_val}' as number",
                    reason="invalid_field_types",
                    preview=str(data)[:200],
                )
        elif not isinstance(score_val, (int, float)):
            raise ModelResponseError(
                f"{judge_name} has invalid overall_score type: expected number, got {type(score_val).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if not 0 <= data["overall_score"] <= 10:
            raise ModelResponseError(
                f"{judge_name} has invalid overall_score value: expected a finite number from 0 to 10",
                reason="invalid_field_values",
                preview=str(data)[:200],
            )

        # Verdict type check
        if not isinstance(data.get("final_verdict"), str):
            raise ModelResponseError(
                f"{judge_name} has invalid final_verdict type: expected string, got {type(data.get('final_verdict')).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )

        # Strengths type check
        if not isinstance(data.get("top_strengths"), list):
            raise ModelResponseError(
                f"{judge_name} has invalid top_strengths type: expected list, got {type(data.get('top_strengths')).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if not all(isinstance(item, str) for item in data["top_strengths"]):
            raise ModelResponseError(
                f"{judge_name} has invalid top_strengths items: expected strings",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )

        # Improvements type check
        if not isinstance(data.get("top_improvements"), list):
            raise ModelResponseError(
                f"{judge_name} has invalid top_improvements type: expected list, got {type(data.get('top_improvements')).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if not all(isinstance(item, str) for item in data["top_improvements"]):
            raise ModelResponseError(
                f"{judge_name} has invalid top_improvements items: expected strings",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
    else:
        # Specialist score type check
        score_val = data.get("score")
        if isinstance(score_val, bool) or score_val is None:
            raise ModelResponseError(
                f"{judge_name} has invalid score type: expected number, got {type(score_val).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if isinstance(score_val, str):
            try:
                data["score"] = float(score_val)
            except ValueError:
                raise ModelResponseError(
                    f"{judge_name} has invalid score type: cannot parse '{score_val}' as number",
                    reason="invalid_field_types",
                    preview=str(data)[:200],
                )
        elif not isinstance(score_val, (int, float)):
            raise ModelResponseError(
                f"{judge_name} has invalid score type: expected number, got {type(score_val).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if not 0 <= data["score"] <= 10:
            raise ModelResponseError(
                f"{judge_name} has invalid score value: expected a finite number from 0 to 10",
                reason="invalid_field_values",
                preview=str(data)[:200],
            )

        # Comments type check
        if not isinstance(data.get("comments"), str):
            raise ModelResponseError(
                f"{judge_name} has invalid comments type: expected string, got {type(data.get('comments')).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )

        # Strengths type check
        if not isinstance(data.get("strengths"), list):
            raise ModelResponseError(
                f"{judge_name} has invalid strengths type: expected list, got {type(data.get('strengths')).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if not all(isinstance(item, str) for item in data["strengths"]):
            raise ModelResponseError(
                f"{judge_name} has invalid strengths items: expected strings",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )

        # Weaknesses type check
        if not isinstance(data.get("weaknesses"), list):
            raise ModelResponseError(
                f"{judge_name} has invalid weaknesses type: expected list, got {type(data.get('weaknesses')).__name__}",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )
        if not all(isinstance(item, str) for item in data["weaknesses"]):
            raise ModelResponseError(
                f"{judge_name} has invalid weaknesses items: expected strings",
                reason="invalid_field_types",
                preview=str(data)[:200],
            )

    return data


from concurrent.futures import ThreadPoolExecutor

MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "2"))
_concurrency_semaphore = None
_thread_pool = None


def get_concurrency_semaphore() -> asyncio.Semaphore:
    """Lazy initialize semaphore within the active asyncio event loop."""
    global _concurrency_semaphore
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _concurrency_semaphore is None or getattr(_concurrency_semaphore, "_loop", None) not in (None, current_loop):
        _concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    return _concurrency_semaphore


def get_thread_pool() -> ThreadPoolExecutor:
    """Dedicated thread pool bounded to MAX_CONCURRENT_CALLS to prevent worker thread exhaustion."""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS, thread_name_prefix="gemini_judge")
    return _thread_pool


def _normalize_finish_reason(finish_reason: Any) -> str:
    """Normalize finish_reason from SDK enum, int, or string to uppercase name."""
    if finish_reason is None:
        return ""
    if hasattr(finish_reason, "name") and isinstance(finish_reason.name, str):
        return finish_reason.name.upper()
    try:
        val = int(finish_reason)
        _REASON_MAP = {
            0: "FINISH_REASON_UNSPECIFIED",
            1: "STOP",
            2: "MAX_TOKENS",
            3: "SAFETY",
            4: "RECITATION",
            5: "OTHER",
            6: "BLOCKLIST",
            7: "PROHIBITED_CONTENT",
            8: "SPII",
            9: "MALFORMED_FUNCTION_CALL",
        }
        if val in _REASON_MAP:
            return _REASON_MAP[val]
    except (ValueError, TypeError):
        pass
    return str(finish_reason).upper()


def _log_response_diagnostics(response, judge_name: str, model_name: str = "unknown") -> None:
    """Log safe, non-sensitive diagnostics about a model response to aid debugging.

    Captures finish reason, block reason (if any), and a short sanitized preview
    of the response text.  Never logs API keys or full user data.
    """
    try:
        # Finish reason (e.g. STOP, MAX_TOKENS, SAFETY, RECITATION)
        finish_reason = None
        block_reason = None
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            finish_reason = getattr(candidate, "finish_reason", None)
            # Some SDK versions expose safety_ratings or block_reason
            block_reason = getattr(candidate, "block_reason", None)
        if hasattr(response, "prompt_feedback"):
            pf = response.prompt_feedback
            if getattr(pf, "block_reason", None):
                block_reason = pf.block_reason

        text_preview = ""
        response_length = None
        response_empty = None
        try:
            raw = response.text or ""
            response_length = len(raw)
            response_empty = not bool(raw.strip())
            text_preview = _sanitize_log_message(raw[:300].replace("\n", " "))
        except Exception:
            text_preview = "<unavailable>"

        logger.info(
            "Judge '%s' [model=%s] response metadata — response_length=%s, empty=%s, finish_reason=%s, block_reason=%s, preview=%.300s",
            judge_name,
            model_name,
            response_length,
            response_empty,
            finish_reason,
            block_reason,
            text_preview,
        )

        # Warn on non-normal finish reasons
        if finish_reason is not None:
            fr_str = _normalize_finish_reason(finish_reason)
            if "MAX_TOKENS" in fr_str or "LENGTH" in fr_str:
                logger.warning(
                    "Judge '%s' response may be truncated (finish_reason=%s).",
                    judge_name,
                    finish_reason,
                )
            elif "SAFETY" in fr_str or "BLOCK" in fr_str:
                logger.warning(
                    "Judge '%s' response was blocked by safety filters (finish_reason=%s, block_reason=%s).",
                    judge_name,
                    finish_reason,
                    block_reason,
                )
    except Exception as diag_exc:
        # Diagnostic logging must never break the main flow.
        logger.debug("Failed to log response diagnostics for '%s': %s", judge_name, diag_exc)


async def call_judge(prompt: str, judge_name: str, abort_event: Optional[asyncio.Event] = None) -> dict:
    """
    Call Gemini with a judge prompt and return parsed JSON response.
    Enforces bounded concurrency across threads, strict timeout per attempt,
    detects 429/ResourceExhausted quota errors, and performs bounded exponential backoff
    honoring the provider's retry delay.
    """
    max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    initial_delay = float(os.getenv("GEMINI_INITIAL_RETRY_DELAY", "2.0"))
    max_delay = float(os.getenv("GEMINI_MAX_RETRY_DELAY", "30.0"))
    backoff_factor = float(os.getenv("GEMINI_BACKOFF_FACTOR", "2.0"))

    last_delay = 10.0
    configured_model = get_configured_model_name()

    # Pre-dispatch check: Do not schedule or dispatch request if daily quota is already exhausted
    if is_daily_quota_exhausted(configured_model):
        info = get_daily_quota_info(configured_model) or {}
        rem = info.get("retry_after", 86400)
        guidance = info.get("guidance") or get_daily_quota_guidance(configured_model, rem)
        logger.warning(
            "Judge '%s' aborting before dispatch — daily quota for model '%s' is already exhausted.",
            judge_name,
            configured_model,
        )
        if abort_event:
            abort_event.set()
        raise GeminiQuotaExceededError(
            f"{judge_name} evaluation prevented: daily API quota is exhausted for model '{configured_model}'. {guidance}",
            retry_after=rem,
            is_daily=True,
            model=configured_model,
            retry_guidance=guidance,
        )

    for attempt in range(max_retries + 1):
        if abort_event and abort_event.is_set():
            logger.info("Judge '%s' aborting before attempt %d — evaluation aborted.", judge_name, attempt + 1)
            raise asyncio.CancelledError(f"{judge_name} aborted before attempt {attempt + 1}")

        if is_daily_quota_exhausted(configured_model):
            info = get_daily_quota_info(configured_model) or {}
            rem = info.get("retry_after", 86400)
            guidance = info.get("guidance") or get_daily_quota_guidance(configured_model, rem)
            if abort_event:
                abort_event.set()
            raise GeminiQuotaExceededError(
                f"{judge_name} evaluation prevented: daily API quota is exhausted for model '{configured_model}'. {guidance}",
                retry_after=rem,
                is_daily=True,
                model=configured_model,
                retry_guidance=guidance,
            )

        semaphore = get_concurrency_semaphore()
        try:
            await semaphore.acquire()
        except asyncio.CancelledError:
            if abort_event:
                abort_event.set()
            raise

        if abort_event and abort_event.is_set():
            semaphore.release()
            raise asyncio.CancelledError(f"{judge_name} aborted after acquire")

        if is_daily_quota_exhausted(configured_model):
            semaphore.release()
            if abort_event:
                abort_event.set()
            info = get_daily_quota_info(configured_model) or {}
            rem = info.get("retry_after", 86400)
            guidance = info.get("guidance") or get_daily_quota_guidance(configured_model, rem)
            raise GeminiQuotaExceededError(
                f"{judge_name} evaluation prevented: daily API quota is exhausted for model '{configured_model}'. {guidance}",
                retry_after=rem,
                is_daily=True,
                model=configured_model,
                retry_guidance=guidance,
            )

        loop = asyncio.get_running_loop()
        released = False

        def release_capacity(*args):
            nonlocal released
            if not released:
                released = True
                loop.call_soon_threadsafe(semaphore.release)

        actual_model_name = configured_model
        fut = None
        start_time = time.perf_counter()
        try:
            model = get_model()
            actual_model_name = getattr(model, "model_name", None) or actual_model_name
            logger.info("Judge '%s' dispatching request to model '%s' (attempt %d/%d).", judge_name, actual_model_name, attempt + 1, max_retries)
            pool = get_thread_pool()
            start_time = time.perf_counter()
            # Let the SDK deadline fire first so its worker exits before the async guard.
            sdk_timeout = _get_sdk_timeout_seconds()
            generate = partial(
                model.generate_content,
                prompt,
                request_options={"timeout": sdk_timeout},
            )
            fut = loop.run_in_executor(pool, generate)
            # Capacity is only freed once the synchronous thread actually completes
            fut.add_done_callback(release_capacity)

            # Shield preserves the worker future so its completion can release capacity.
            response = await asyncio.wait_for(asyncio.shield(fut), timeout=TIMEOUT_SECONDS)
            elapsed = time.perf_counter() - start_time
            logger.info("Judge '%s' [model=%s] response received in %.2fs (attempt %d/%d).", judge_name, actual_model_name, elapsed, attempt + 1, max_retries)

            # Log diagnostic metadata before attempting to parse.
            _log_response_diagnostics(response, judge_name, actual_model_name)

            # Detect empty / blocked responses.
            response_text = None
            try:
                response_text = response.text if response else None
            except Exception:
                pass

            candidate = response.candidates[0] if (hasattr(response, "candidates") and response.candidates) else None
            finish_reason = getattr(candidate, "finish_reason", None) if candidate else None
            fr_str = _normalize_finish_reason(finish_reason)
            if not response_text:
                # Check if the response was blocked.
                block_reason = None
                try:
                    if hasattr(response, "prompt_feedback"):
                        block_reason = getattr(response.prompt_feedback, "block_reason", None)
                    if block_reason is None and hasattr(response, "candidates") and response.candidates:
                        block_reason = getattr(response.candidates[0], "block_reason", None)
                except Exception:
                    pass

                if block_reason or "SAFETY" in fr_str or "BLOCK" in fr_str or "RECITATION" in fr_str:
                    logger.warning(
                        "Judge '%s' [model=%s] response was blocked — response_length=0, finish_reason=%s, block_reason=%s",
                        judge_name,
                        actual_model_name,
                        finish_reason,
                        block_reason,
                    )
                    raise ModelResponseError(
                        f"{judge_name} response was blocked (reason: {block_reason or finish_reason}).",
                        reason="blocked",
                    )
                logger.warning(
                    "Judge '%s' [model=%s] returned an empty response — response_length=0, finish_reason=%s",
                    judge_name,
                    actual_model_name,
                    finish_reason,
                )
                raise ModelResponseError(
                    f"{judge_name} returned an empty response.",
                    reason="empty_response",
                )

            # Classify safety blocks and truncation before parsing; a syntactically
            # complete prefix is still not a complete response when token-limited.
            safe_preview = _sanitize_log_message(response_text[:300].replace("\n", " "))
            if "SAFETY" in fr_str or "BLOCK" in fr_str or "RECITATION" in fr_str:
                logger.warning(
                    "Judge '%s' [model=%s] response blocked by safety filters — response_length=%d, finish_reason=%s, preview=%.300s",
                    judge_name,
                    actual_model_name,
                    len(response_text),
                    finish_reason,
                    safe_preview,
                )
                raise ModelResponseError(
                    f"{judge_name} response was blocked (finish_reason={finish_reason}).",
                    reason="blocked",
                    preview=safe_preview,
                )
            if "MAX_TOKENS" in fr_str or "LENGTH" in fr_str:
                logger.warning(
                    "Judge '%s' [model=%s] response truncated by token limit — response_length=%d, finish_reason=%s, preview=%.300s",
                    judge_name,
                    actual_model_name,
                    len(response_text),
                    finish_reason,
                    safe_preview,
                )
                raise ModelResponseError(
                    f"{judge_name} response was truncated by token limit (finish_reason={finish_reason}).",
                    reason="truncated",
                    preview=safe_preview,
                )
            else:
                logger.info(
                    "Judge '%s' [model=%s] parsing response — response_length=%d, empty=%s, finish_reason=%s, block_reason=%s, preview=%.300s",
                    judge_name,
                    actual_model_name,
                    len(response_text),
                    not bool(response_text.strip()),
                    finish_reason,
                    getattr(candidate, "block_reason", None) if candidate else None,
                    safe_preview,
                )
                try:
                    result = extract_json_from_response(response_text, model_name=actual_model_name)
                except ModelResponseError as parse_error:
                    parse_exc = getattr(parse_error, "parse_exception", None) or parse_error.__cause__
                    exc_str = f"{type(parse_exc).__name__}: {parse_exc}" if parse_exc else "None"
                    logger.warning(
                        "Judge '%s' [model=%s] response parsing failed — response_length=%d, finish_reason=%s, reason=%s, error=%s, parsing_exception=%s, preview=%.300s",
                        judge_name,
                        actual_model_name,
                        len(response_text),
                        finish_reason,
                        parse_error.reason,
                        _sanitize_log_message(str(parse_error)),
                        _sanitize_log_message(exc_str),
                        safe_preview,
                    )
                    raise

            logger.debug(
                "Judge '%s' parsed JSON structure — keys: %s",
                judge_name,
                list(result.keys()) if isinstance(result, dict) else type(result).__name__,
            )
            try:
                result = validate_judge_schema(result, judge_name)
            except ModelResponseError as schema_error:
                logger.warning(
                    "Judge '%s' [model=%s] schema validation failed — response_length=%d, reason=%s, error=%s, preview=%.300s",
                    judge_name,
                    actual_model_name,
                    len(response_text),
                    schema_error.reason,
                    _sanitize_log_message(str(schema_error)),
                    safe_preview,
                )
                raise
            total_elapsed = time.perf_counter() - start_time
            logger.info("Judge '%s' [model=%s] evaluation completed successfully in %.2fs.", judge_name, actual_model_name, total_elapsed)
            return result

        except asyncio.CancelledError:
            # Task cancelled by caller or sibling error; re-raise immediately
            if fut is None:
                release_capacity()
            if abort_event:
                abort_event.set()
            raise
        except asyncio.TimeoutError as exc:
            elapsed = time.perf_counter() - start_time
            underlying_exception = None
            if fut is not None and fut.done() and not fut.cancelled():
                try:
                    underlying_exception = fut.exception()
                except asyncio.CancelledError:
                    pass
            timeout_source = (
                "gemini_sdk"
                if underlying_exception is not None
                else "application_asyncio_wait_for"
            )
            underlying_type = (
                type(underlying_exception).__name__
                if underlying_exception is not None
                else "not_available"
            )
            underlying_message = (
                _sanitize_log_message(str(underlying_exception))
                if underlying_exception is not None
                else "not_available"
            )
            logger.warning(
                "Judge '%s' [model=%s] category=timeout timeout_source=%s "
                "elapsed=%.2fs limit=%.1fs underlying_exception_type=%s "
                "underlying_exception=%s",
                judge_name,
                actual_model_name,
                timeout_source,
                elapsed,
                TIMEOUT_SECONDS,
                underlying_type,
                underlying_message,
            )
            if abort_event:
                abort_event.set()
            err = TimeoutError(f"{judge_name} timed out after {TIMEOUT_SECONDS} seconds.")
            setattr(err, "judge_name", judge_name)
            setattr(err, "elapsed", elapsed)
            setattr(err, "model_name", actual_model_name)
            setattr(err, "timeout_source", timeout_source)
            setattr(err, "underlying_exception_type", underlying_type)
            if underlying_exception is not None:
                raise err from underlying_exception
            raise err from exc
        except EnvironmentError as e:
            logger.error("Judge '%s' [model=%s] category=environment_error: %s", judge_name, actual_model_name, _sanitize_log_message(str(e)), exc_info=True)
            if abort_event:
                abort_event.set()
            raise
        except ModelResponseError as e:
            logger.error(
                "Judge '%s' [model=%s] category=model_response_error (%s): %s; preview=%.300s",
                judge_name,
                actual_model_name,
                e.reason,
                _sanitize_log_message(str(e)),
                _sanitize_log_message(getattr(e, "preview", "")),
                exc_info=True,
            )
            if abort_event:
                abort_event.set()
            raise
        except ValueError as e:
            logger.error("Judge '%s' [model=%s] category=validation_error: %s", judge_name, actual_model_name, _sanitize_log_message(str(e)), exc_info=True)
            if abort_event:
                abort_event.set()
            raise
        except Exception as exc:
            sanitized_msg = _sanitize_log_message(f"{type(exc).__name__}: {str(exc)}")

            # The SDK can report its own transport deadline before the async guard fires.
            if DeadlineExceeded is not None and isinstance(exc, DeadlineExceeded):
                elapsed = time.perf_counter() - start_time
                logger.warning(
                    "Judge '%s' [model=%s] category=timeout timeout_source=gemini_sdk "
                    "elapsed=%.2fs limit=%.1fs underlying_exception_type=%s "
                    "underlying_exception=%s",
                    judge_name,
                    actual_model_name,
                    elapsed,
                    TIMEOUT_SECONDS,
                    type(exc).__name__,
                    _sanitize_log_message(str(exc)),
                )
                if abort_event:
                    abort_event.set()
                err = TimeoutError(f"{judge_name} timed out after {elapsed:.2f} seconds.")
                setattr(err, "judge_name", judge_name)
                setattr(err, "elapsed", elapsed)
                setattr(err, "model_name", actual_model_name)
                setattr(err, "timeout_source", "gemini_sdk")
                setattr(err, "underlying_exception_type", type(exc).__name__)
                raise err from exc

            # 1. Check for 403 Permission / Authentication error (Non-retryable)
            if is_permission_error(exc):
                logger.error("Judge '%s' [model=%s] category=permission_denied (403): %s", judge_name, actual_model_name, sanitized_msg, exc_info=True)
                if abort_event:
                    abort_event.set()
                raise GeminiPermissionError(
                    f"{judge_name} evaluation failed: Gemini API permission denied (403). Please verify GEMINI_API_KEY."
                ) from exc

            # 2. Check for 429 Quota Exceeded / Rate Limit
            if is_quota_error(exc):
                is_daily = is_daily_quota_error(exc)
                if is_daily:
                    provider_delay = extract_provider_retry_delay(exc)
                    retry_secs = provider_delay if (provider_delay is not None and provider_delay > 0) else 86400
                    mark_daily_quota_exhausted(actual_model_name, retry_after=retry_secs, message=sanitized_msg)
                    guidance = get_daily_quota_guidance(actual_model_name, retry_secs)
                    logger.error(
                        "Judge '%s' [model=%s] category=daily_quota_exhausted (429): %s",
                        judge_name, actual_model_name, sanitized_msg, exc_info=True
                    )
                    if abort_event:
                        abort_event.set()
                    raise GeminiQuotaExceededError(
                        f"{judge_name} evaluation failed: daily API quota exhausted for model '{actual_model_name}'. {guidance}",
                        retry_after=retry_secs,
                        is_daily=True,
                        model=actual_model_name,
                        retry_guidance=guidance,
                    ) from exc

                provider_delay = extract_provider_retry_delay(exc)
                delay = extract_retry_delay(
                    exc,
                    attempt=attempt,
                    initial_delay=initial_delay,
                    max_delay=max_delay,
                    backoff_factor=backoff_factor,
                )
                last_delay = delay

                # Requirement 1: Parse Google's retry_delay correctly and never retry earlier than
                # the provider-requested delay. Apply any configured maximum carefully; if the requested
                # delay exceeds it, fail gracefully rather than retry early.
                effective_delay = provider_delay if provider_delay is not None else delay
                if effective_delay > max_delay:
                    guidance = get_transient_rate_limit_guidance(actual_model_name, effective_delay)
                    logger.warning(
                        "Judge '%s' [model=%s] category=rate_limit_exceeds_max_delay (429). "
                        "Provider requested delay (%.2fs) exceeds configured maximum retry delay (%.2fs). "
                        "Failing gracefully without retrying early: %s",
                        judge_name, actual_model_name, effective_delay, max_delay, sanitized_msg
                    )
                    if abort_event:
                        abort_event.set()
                    raise GeminiQuotaExceededError(
                        f"{judge_name} evaluation failed due to API quota rate limit for model '{actual_model_name}'. "
                        f"Requested retry delay ({effective_delay:.1f}s) exceeds maximum allowed delay ({max_delay:.1f}s). {guidance}",
                        retry_after=int(math.ceil(effective_delay)),
                        is_daily=False,
                        model=actual_model_name,
                        retry_guidance=guidance,
                    ) from exc

                if attempt < max_retries:
                    logger.warning(
                        "Judge '%s' [model=%s] category=transient_rate_limit (429) (attempt %d/%d). Retrying in %.2fs: %s",
                        judge_name, actual_model_name, attempt + 1, max_retries, delay, sanitized_msg
                    )
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        if abort_event:
                            abort_event.set()
                        raise
                    continue
                else:
                    guidance = get_transient_rate_limit_guidance(actual_model_name, last_delay)
                    logger.error(
                        "Judge '%s' [model=%s] category=rate_limit_retries_exhausted (429) (%d attempts): %s",
                        judge_name, actual_model_name, max_retries + 1, sanitized_msg, exc_info=True
                    )
                    if abort_event:
                        abort_event.set()
                    raise GeminiQuotaExceededError(
                        f"{judge_name} evaluation failed due to API quota limits for model '{actual_model_name}'. {guidance}",
                        retry_after=int(math.ceil(last_delay)),
                        is_daily=False,
                        model=actual_model_name,
                        retry_guidance=guidance,
                    ) from exc

            # 3. Check for 503 Service Unavailable (Retryable with backoff)
            if is_service_unavailable_error(exc):
                provider_delay = extract_provider_retry_delay(exc)
                delay = extract_retry_delay(
                    exc,
                    attempt=attempt,
                    initial_delay=initial_delay,
                    max_delay=max_delay,
                    backoff_factor=backoff_factor,
                )
                effective_delay = provider_delay if provider_delay is not None else delay
                if effective_delay > max_delay:
                    logger.warning(
                        "Judge '%s' [model=%s] category=service_unavailable_exceeds_max_delay (503). "
                        "Requested delay (%.2fs) exceeds max delay (%.2fs). Failing gracefully: %s",
                        judge_name, actual_model_name, effective_delay, max_delay, sanitized_msg
                    )
                    if abort_event:
                        abort_event.set()
                    raise GeminiServiceUnavailableError(
                        f"{judge_name} evaluation failed: Gemini service temporarily unavailable (503)."
                    ) from exc

                if attempt < max_retries:
                    logger.warning(
                        "Judge '%s' [model=%s] category=service_unavailable (503) (attempt %d/%d). Retrying in %.2fs: %s",
                        judge_name, actual_model_name, attempt + 1, max_retries, delay, sanitized_msg
                    )
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        if abort_event:
                            abort_event.set()
                        raise
                    continue
                else:
                    logger.error(
                        "Judge '%s' [model=%s] category=service_unavailable_retries_exhausted (503) (%d attempts): %s",
                        judge_name, actual_model_name, max_retries + 1, sanitized_msg, exc_info=True
                    )
                    if abort_event:
                        abort_event.set()
                    raise GeminiServiceUnavailableError(
                        f"{judge_name} evaluation failed: Gemini service temporarily unavailable (503)."
                    ) from exc

            # 4. Non-retryable runtime failures: prevent leaking secrets or stack traces to caller
            logger.error("Judge '%s' [model=%s] category=unknown_runtime_error: %s", judge_name, actual_model_name, sanitized_msg, exc_info=True)
            if abort_event:
                abort_event.set()
            raise RuntimeError(f"{judge_name} evaluation failed. Service temporarily unavailable.") from exc
