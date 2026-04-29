import json
import os
import time
from typing import Optional
from dotenv import load_dotenv
from google import genai

load_dotenv()

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
MAX_RETRIES = max(1, int(os.getenv("GEMINI_MAX_RETRIES", "1")))
RETRY_BASE_SEC = float(os.getenv("GEMINI_RETRY_BASE_SEC", "1.5"))


def gemini_is_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _safe_json_loads(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def gemini_generate_json(prompt: str, schema: dict, *, temperature: float = 0.2, model: Optional[str] = None):
    if not gemini_is_available():
        print("[gemini] API key not found. Skipping LLM planning.")
        return None

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    model_name = model or DEFAULT_MODEL
    fallback_used = False
    last_exc = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                    "response_json_schema": schema,
                },
            )
            data = _safe_json_loads(getattr(response, "text", ""))
            if data is None:
                print("[gemini] Response was not valid JSON.")
            return data
        except Exception as exc:
            last_exc = exc
            message = str(exc)
            exhausted = "RESOURCE_EXHAUSTED" in message or "429" in message
            if exhausted and not fallback_used and FALLBACK_MODEL and FALLBACK_MODEL != model_name:
                print(f"[gemini] Quota exhausted for {model_name}. Falling back to {FALLBACK_MODEL}.")
                model_name = FALLBACK_MODEL
                fallback_used = True
                continue
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_SEC * (attempt + 1))
                continue

    if last_exc:
        print(f"[gemini] Request failed: {last_exc}")
    return None
