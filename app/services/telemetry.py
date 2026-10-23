import asyncio
import logging
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 10.0
_cache_at = 0.0
_cache_data: Optional[dict] = None


def _gpu_memory() -> tuple[Optional[float], Optional[float]]:
    """Read VRAM from nvidia-smi when the server host exposes a GPU."""
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=1.5,
            text=True,
        ).strip().splitlines()[0]
        used, total = [float(part.strip()) for part in output.split(",")[:2]]
        return round(used / 1024, 2), round(total / 1024, 2)
    except Exception:
        return None, None


async def _probe() -> dict:
    base_url = settings.LOCAL_LLM_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.LOCAL_LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LOCAL_LLM_MODEL,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "temperature": 0.0,
        "max_tokens": 8,
    }

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=8.0) as client:
        models_res, chat_res = await asyncio.gather(
            client.get(f"{base_url}/models", headers=headers),
            client.post(f"{base_url}/chat/completions", json=payload, headers=headers),
        )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    model_info = {}
    if models_res.status_code == 200:
        models = models_res.json().get("data") or []
        if models:
            model_info = models[0]
    meta = model_info.get("meta") or {}
    size_bytes = meta.get("size") or model_info.get("size") or 0

    timings = {}
    usage = {}
    online = chat_res.status_code == 200
    if online:
        body = chat_res.json()
        timings = body.get("timings") or {}
        usage = body.get("usage") or {}

    used_gb, total_gb = await asyncio.to_thread(_gpu_memory)

    return {
        "status": "online" if online else "offline",
        "model": model_info.get("id") or settings.LOCAL_LLM_MODEL,
        "quantization": meta.get("ftype"),
        "model_size_gb": round(size_bytes / 1e9, 2) if size_bytes else None,
        "context_size": meta.get("n_ctx"),
        "tokens_per_second": round(timings.get("predicted_per_second", 0.0), 1) if timings else None,
        "prompt_tokens_per_second": round(timings.get("prompt_per_second", 0.0), 1) if timings else None,
        "latency_ms": latency_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "vram_used_gb": used_gb,
        "vram_total_gb": total_gb,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_gemma_telemetry(force: bool = False) -> dict:
    global _cache_at, _cache_data
    now = time.monotonic()
    if not force and _cache_data is not None and (now - _cache_at) < _CACHE_TTL_SECONDS:
        return _cache_data

    try:
        data = await _probe()
    except Exception as exc:
        logger.debug("Gemma telemetry probe failed: %s", exc)
        data = {
            "status": "offline",
            "model": settings.LOCAL_LLM_MODEL,
            "quantization": None,
            "model_size_gb": None,
            "context_size": None,
            "tokens_per_second": None,
            "prompt_tokens_per_second": None,
            "latency_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "vram_used_gb": None,
            "vram_total_gb": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    _cache_at = now
    _cache_data = data
    return data
