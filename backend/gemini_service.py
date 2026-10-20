import google.generativeai as genai
import json
import os
import re
import asyncio
from dotenv import load_dotenv

load_dotenv()

_configured = False
TIMEOUT_SECONDS = 30.0


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


def get_model():
    _configure_gemini()
    return genai.GenerativeModel(
        model_name="gemini-3.1-flash-lite",
        generation_config=genai.types.GenerationConfig(
            temperature=0.4,
            top_p=0.95,
            max_output_tokens=2048,
        ),
    )


def extract_json_from_response(text: str) -> dict:
    """Robustly extract JSON from model response."""
    text = text.strip()

    # Remove markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse structured evaluation output.")


from concurrent.futures import ThreadPoolExecutor

MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "4"))
_concurrency_semaphore = None
_thread_pool = None


def get_concurrency_semaphore() -> asyncio.Semaphore:
    """Lazy initialize semaphore within the active asyncio event loop."""
    global _concurrency_semaphore
    if _concurrency_semaphore is None:
        _concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    return _concurrency_semaphore


def get_thread_pool() -> ThreadPoolExecutor:
    """Dedicated thread pool bounded to MAX_CONCURRENT_CALLS to prevent worker thread exhaustion."""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS, thread_name_prefix="gemini_judge")
    return _thread_pool


async def call_judge(prompt: str, judge_name: str) -> dict:
    """
    Call Gemini with a judge prompt and return parsed JSON response.
    Enforces bounded concurrency across threads, strict 30-second timeout,
    and prevents capacity release before the underlying synchronous thread finishes.
    """
    semaphore = get_concurrency_semaphore()
    await semaphore.acquire()

    loop = asyncio.get_running_loop()
    released = False

    def release_capacity(*args):
        nonlocal released
        if not released:
            released = True
            loop.call_soon_threadsafe(semaphore.release)

    try:
        model = get_model()
        pool = get_thread_pool()
        # Submit to bounded thread pool
        fut = loop.run_in_executor(pool, model.generate_content, prompt)
        # Capacity is only freed once the synchronous thread actually completes
        fut.add_done_callback(release_capacity)

        # Execute with strict timeout; shield prevents cancelling fut prematurely
        response = await asyncio.wait_for(asyncio.shield(fut), timeout=TIMEOUT_SECONDS)

        if not response or not response.text:
            raise ValueError(f"{judge_name} returned an empty response.")

        result = extract_json_from_response(response.text)
        return result

    except asyncio.TimeoutError:
        raise TimeoutError(f"{judge_name} timed out after {TIMEOUT_SECONDS} seconds.")
    except EnvironmentError:
        raise
    except ValueError:
        raise
    except Exception:
        # Prevent leaking API keys, internal network endpoints, or stack traces
        raise RuntimeError(f"{judge_name} evaluation failed. Service temporarily unavailable.")
