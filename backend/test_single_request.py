import os
import sys
import time
import hashlib
from dotenv import load_dotenv

# Ensure backend .env is loaded
load_dotenv()

import google.generativeai as genai
from gemini_service import get_model, _sanitize_log_message

def run_diagnostic():
    print("=" * 60)
    print("DIAGNOSTIC TEST: Single Short Request to Configured Gemini Model")
    print("=" * 60)

    # 1. Verify environment variable
    env_var_name = "GEMINI_API_KEY"
    raw_key = os.getenv(env_var_name, "").strip()
    if not raw_key:
        print(f"ERROR: {env_var_name} is empty or not set in environment.")
        return
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()[:8]
    print(f"API Key Environment Variable: {env_var_name}")
    print(f"API Key Loaded: len={len(raw_key)}, prefix={raw_key[:6]}..., sha256_8={key_hash}")

    # Model name
    configured_model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash (default fallback)"
    print(f"Configured Model: {configured_model}")

    # 2. Initialize model through backend's own get_model()
    try:
        model = get_model()
        model_name = getattr(model, "model_name", "unknown")
        print(f"Active GenerativeModel: {model_name}")
    except Exception as e:
        print(f"Failed to instantiate model: {type(e).__name__}: {_sanitize_log_message(str(e))}")
        return

    # 3. Send exactly ONE short request
    prompt = "Ping. Respond with exactly one word: Pong."
    print(f"Sending 1 short prompt: '{prompt}'...")
    start_time = time.time()
    try:
        response = model.generate_content(
            prompt,
            request_options={"timeout": 60.0}
        )
        elapsed = time.time() - start_time
        print(f"Status: HTTP 200 OK (Duration: {elapsed:.2f}s)")
        print(f"Model: {model_name}")
        response_text = response.text if response and hasattr(response, "text") else "No text"
        print(f"Provider Response: {_sanitize_log_message(response_text.strip())}")
    except Exception as exc:
        elapsed = time.time() - start_time
        print(f"Request Failed after {elapsed:.2f}s")
        print(f"Exception Type: {type(exc).__name__}")

        status_code = getattr(exc, "code", None)
        if callable(status_code):
            try:
                status_code = status_code()
            except Exception:
                status_code = None
        if not status_code:
            status_code = getattr(exc, "status_code", getattr(exc, "grpc_status_code", "N/A"))
        print(f"HTTP/Status Code: {status_code}")
        print(f"Sanitized Error Message: {_sanitize_log_message(str(exc))}")

if __name__ == "__main__":
    run_diagnostic()
