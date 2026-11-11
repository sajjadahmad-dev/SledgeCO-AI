import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
H = {"x-goog-api-key": os.getenv("GEMINI_API_KEY", "")}
body = {"contents": [{"parts": [{"text": "Reply with the single word: OK"}]}],
        "generationConfig": {"temperature": 0}}

for model in ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash",
              "gemini-flash-lite-latest", "gemini-3.5-flash-lite"]:
    t = time.perf_counter()
    try:
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       headers=H, json=body, timeout=25)
        print(f"{model:28s} HTTP {r.status_code} in {time.perf_counter() - t:5.1f}s  {r.text[:60].strip()!r}")
    except Exception as exc:
        print(f"{model:28s} FAILED {type(exc).__name__} after {time.perf_counter() - t:.1f}s")