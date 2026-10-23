"""Measure the local llama-server path used by Hermes.

Run with the server already listening on LOCAL_LLM_URL:

    uv run python scripts/bench_gemma.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services.gemma_client import gemma_client


async def probe() -> dict:
    base_url = settings.LOCAL_LLM_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.LOCAL_LLM_API_KEY}"}
    payload = {
        "model": settings.LOCAL_LLM_MODEL,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "temperature": 0.0,
        "max_tokens": 8,
    }
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=15.0) as client:
        models_res, chat_res = await asyncio.gather(
            client.get(f"{base_url}/models", headers=headers),
            client.post(f"{base_url}/chat/completions", json=payload, headers=headers),
        )
    wall_ms = (time.perf_counter() - started) * 1000
    model = (models_res.json().get("data") or [{}])[0] if models_res.status_code == 200 else {}
    body = chat_res.json() if chat_res.status_code == 200 else {}
    timings = body.get("timings") or {}
    meta = model.get("meta") or {}
    return {
        "status": "online" if body else "offline",
        "model": model.get("id") or settings.LOCAL_LLM_MODEL,
        "quantization": meta.get("ftype"),
        "weights_gb": round((meta.get("size") or 0) / 1e9, 2),
        "predicted_tokens_per_second": round(timings.get("predicted_per_second", 0.0), 1),
        "prompt_tokens_per_second": round(timings.get("prompt_per_second", 0.0), 1),
        "wall_ms": round(wall_ms, 1),
    }


async def main():
    print(json.dumps(await probe(), indent=2))

    started = time.perf_counter()
    extraction = await gemma_client.extract_email_task(
        sender="Prof. Menon <menon@example.edu>",
        subject="CS401: Distributed Systems - Lab 3 Submission Cutoff Tonight",
        body="Lab 3 consensus engine is due tonight by 11:59 PM on Classroom.",
        email_received_at_ist="2026-10-23 20:00:00 IST",
    )
    extraction_ms = (time.perf_counter() - started) * 1000
    print(json.dumps({
        "task": "email_extraction",
        "latency_ms": round(extraction_ms, 1),
        "category": extraction.get("category"),
        "deadline_text": extraction.get("deadline_text"),
        "exact_deadline_iso": extraction.get("exact_deadline_iso"),
    }, indent=2))

    started = time.perf_counter()
    script = await gemma_client.generate_briefing_script(
        panic_items=[{"title": "CS401 Lab 3", "source": "CS401", "hours_left": 3.7}],
        imminent_items=[{"title": "CS205 Homework 2", "source": "CS205", "hours_left": 21.7}],
        top_opp={"title": "Google Summer of Code 2027", "organizer": "Google Open Source"},
    )
    briefing_ms = (time.perf_counter() - started) * 1000
    print(json.dumps({
        "task": "briefing_script",
        "latency_ms": round(briefing_ms, 1),
        "characters": len(script),
        "preview": script[:160],
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
