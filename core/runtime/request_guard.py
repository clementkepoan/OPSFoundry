from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256
from threading import Lock
from time import time

from core.config.settings import Settings


def _hash_key(prefix: str, value: str) -> str:
    digest = sha256(value.encode("utf-8")).hexdigest()
    return f"opsfoundry:req:{prefix}:{digest}"


def build_upload_request_key(
    workflow_name: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    client_key: str | None = None,
) -> str:
    basis = client_key or f"{workflow_name}:{filename}:{content_type}:{size_bytes}"
    return _hash_key("upload", basis)


def build_work_item_request_key(
    action: str,
    work_item_id: str,
    qualifier: str | None = None,
    client_key: str | None = None,
) -> str:
    basis = client_key or ":".join(part for part in [action, work_item_id, qualifier] if part)
    return _hash_key(action, basis)


class BaseRequestGuard(ABC):
    @abstractmethod
    def claim(self, key: str, ttl_seconds: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear(self, key: str) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def backend(self) -> str:
        raise NotImplementedError


class InMemoryRequestGuard(BaseRequestGuard):
    def __init__(self) -> None:
        self._entries: dict[str, float] = {}
        self._lock = Lock()

    @property
    def backend(self) -> str:
        return "memory"

    def claim(self, key: str, ttl_seconds: int) -> bool:
        now = time()
        with self._lock:
            self._entries = {name: expiry for name, expiry in self._entries.items() if expiry > now}
            if self._entries.get(key, 0) > now:
                return False
            self._entries[key] = now + ttl_seconds
            return True

    def clear(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


class RedisRequestGuard(BaseRequestGuard):
    def __init__(self, client) -> None:
        self.client = client

    @property
    def backend(self) -> str:
        return "redis"

    def claim(self, key: str, ttl_seconds: int) -> bool:
        return bool(self.client.set(key, "1", ex=ttl_seconds, nx=True))

    def clear(self, key: str) -> None:
        self.client.delete(key)


def build_request_guard(settings: Settings) -> BaseRequestGuard:
    try:
        from redis import Redis
        from redis.exceptions import RedisError

        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=0.2,
            socket_connect_timeout=0.2,
        )
        client.ping()
        return RedisRequestGuard(client)
    except Exception:
        return InMemoryRequestGuard()
