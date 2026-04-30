from __future__ import annotations

import os
from typing import Any

import json

from platform_cache import cache_delete
from platform_support import PLATFORM_EVENTS_PATH, append_jsonl, ensure_platform_data_dir, read_jsonl


def publish_event(topic: str, payload: dict[str, Any], source: str = "dashboard") -> dict[str, Any]:
    ensure_platform_data_dir()
    event = append_jsonl(PLATFORM_EVENTS_PATH, {
        "topic": topic,
        "source": source,
        "payload": payload,
    })

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis  # type: ignore

            redis.Redis.from_url(redis_url, decode_responses=True).publish(
                "evonexus:platform",
                json.dumps(event, ensure_ascii=False),
            )
        except Exception:
            pass

    for cache_key in (
        "providers:list",
        "observability:summary",
        "observability:providers",
        "platform:queue:50",
    ):
        try:
            cache_delete(cache_key)
        except Exception:
            pass

    return event


def list_events(limit: int = 100, topics: list[str] | None = None) -> list[dict[str, Any]]:
    events = read_jsonl(PLATFORM_EVENTS_PATH, limit=limit)
    if topics:
        allowed = set(topics)
        events = [event for event in events if event.get("topic") in allowed]
    return events


def queue_status() -> dict[str, Any]:
    events = read_jsonl(PLATFORM_EVENTS_PATH, limit=200)
    latest = events[-1] if events else None
    return {
        "backend": "file",
        "path": str(PLATFORM_EVENTS_PATH),
        "event_count": len(events),
        "latest_event": latest,
    }
