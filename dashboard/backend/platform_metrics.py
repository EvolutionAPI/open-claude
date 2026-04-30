from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from platform_support import PROVIDER_METRICS_PATH, append_jsonl, read_jsonl


def record_provider_event(
    *,
    provider_id: str,
    event: str,
    model: str | None = None,
    latency_ms: float | None = None,
    success: bool | None = None,
    detail: str | None = None,
    mode: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_id": provider_id,
        "event": event,
        "model": model,
        "latency_ms": latency_ms,
        "success": success,
        "detail": detail,
        "mode": mode,
        "metadata": metadata or {},
    }
    return append_jsonl(PROVIDER_METRICS_PATH, payload)


def load_provider_events(limit: int = 500) -> list[dict[str, Any]]:
    return read_jsonl(PROVIDER_METRICS_PATH, limit=limit)


def summarize_provider_events(limit: int = 500) -> dict[str, Any]:
    events = load_provider_events(limit=limit)
    by_provider: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "events": 0,
        "successes": 0,
        "failures": 0,
        "latencies": [],
        "models": defaultdict(lambda: {"events": 0, "successes": 0, "failures": 0, "latencies": []}),
        "last_event": None,
    })

    for event in events:
        provider_id = event.get("provider_id") or "unknown"
        provider_bucket = by_provider[provider_id]
        provider_bucket["events"] += 1
        provider_bucket["last_event"] = event
        model = event.get("model") or "unknown"
        model_bucket = provider_bucket["models"][model]
        model_bucket["events"] += 1
        if event.get("success") is True:
            provider_bucket["successes"] += 1
            model_bucket["successes"] += 1
        elif event.get("success") is False:
            provider_bucket["failures"] += 1
            model_bucket["failures"] += 1
        latency = event.get("latency_ms")
        if isinstance(latency, (int, float)):
            provider_bucket["latencies"].append(float(latency))
            model_bucket["latencies"].append(float(latency))

    summary = []
    for provider_id, bucket in by_provider.items():
        latencies = bucket.pop("latencies")
        models = []
        for model_id, model_bucket in bucket.pop("models").items():
            model_latencies = model_bucket.pop("latencies")
            model_bucket["avg_latency_ms"] = round(mean(model_latencies), 2) if model_latencies else None
            models.append({"model": model_id, **model_bucket})
        bucket["avg_latency_ms"] = round(mean(latencies), 2) if latencies else None
        bucket["success_rate"] = round((bucket["successes"] / bucket["events"]) * 100, 1) if bucket["events"] else None
        bucket["models"] = sorted(models, key=lambda row: (-row["events"], row["model"]))
        summary.append({"provider_id": provider_id, **bucket})

    summary.sort(key=lambda row: (-row["events"], row["provider_id"]))
    return {
        "events": events[-100:],
        "providers": summary,
        "total_events": len(events),
    }

