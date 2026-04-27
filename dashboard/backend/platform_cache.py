from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable


_lock = threading.Lock()
_memory_cache: dict[str, tuple[float | None, Any]] = {}


@dataclass(frozen=True)
class CacheStatus:
    backend: str
    available: bool
    detail: str | None = None


class _MemoryCacheBackend:
    backend = "memory"

    def get(self, key: str) -> Any:
        now = time.time()
        with _lock:
            item = _memory_cache.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at is not None and expires_at < now:
                _memory_cache.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = (time.time() + ttl) if ttl else None
        with _lock:
            _memory_cache[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with _lock:
            _memory_cache.pop(key, None)

    def clear(self) -> None:
        with _lock:
            _memory_cache.clear()

    def status(self) -> CacheStatus:
        with _lock:
            size = len(_memory_cache)
        return CacheStatus(backend="memory", available=True, detail=f"{size} entries")


class _RedisCacheBackend:
    backend = "redis"

    def __init__(self, url: str):
        import redis  # type: ignore

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = "evonexus:platform:cache:"
        self._redis.ping()

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Any:
        raw = self._redis.get(self._key(key))
        return None if raw is None else json.loads(raw)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        if ttl:
            self._redis.setex(self._key(key), ttl, payload)
        else:
            self._redis.set(self._key(key), payload)

    def delete(self, key: str) -> None:
        self._redis.delete(self._key(key))

    def clear(self) -> None:
        for key in self._redis.scan_iter(match=f"{self._prefix}*"):
            self._redis.delete(key)

    def status(self) -> CacheStatus:
        try:
            pong = self._redis.ping()
            return CacheStatus(backend="redis", available=bool(pong), detail=os.environ.get("REDIS_URL"))
        except Exception as exc:
            return CacheStatus(backend="redis", available=False, detail=str(exc)[:200])


@lru_cache(maxsize=1)
def _get_backend() -> Any:
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            return _RedisCacheBackend(redis_url)
        except Exception:
            pass
    return _MemoryCacheBackend()


def cache_get(key: str) -> Any:
    return _get_backend().get(key)


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    _get_backend().set(key, value, ttl)


def cache_delete(key: str) -> None:
    _get_backend().delete(key)


def cache_get_or_set(key: str, loader: Callable[[], Any], ttl: int | None = None) -> Any:
    cached = cache_get(key)
    if cached is not None:
        return cached
    value = loader()
    cache_set(key, value, ttl=ttl)
    return value


def cache_status() -> dict[str, Any]:
    status = _get_backend().status()
    return {
        "backend": status.backend,
        "available": status.available,
        "detail": status.detail,
    }

