"""Bounded, process-local rate limiting for AI-backed requests."""

import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional


DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_REQUESTS = 10
MAX_TRACKED_CLIENTS = 10_000
MAX_WINDOW_SECONDS = 86_400
MAX_REQUESTS = 10_000


@dataclass
class _Window:
    started_at: float
    request_count: int


def _configuration_value(
    environ: Mapping[str, str],
    name: str,
    default: int,
    maximum: int,
) -> int:
    raw_value = environ.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    if value < 1 or value > maximum:
        return default
    return value


def trusted_proxy_count(raw_value: Optional[str], *, maximum: int = 5) -> int:
    """Return the explicitly trusted X-Forwarded-For hop count, or disable it."""
    if raw_value is None:
        return 0
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 0
    if value < 1 or value > maximum:
        return 0
    return value


class AIRateLimiter:
    """Allow a bounded number of requests per client in a fixed time window."""

    def __init__(
        self,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        *,
        max_clients: int = MAX_TRACKED_CLIENTS,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, int)
            or not 1 <= window_seconds <= MAX_WINDOW_SECONDS
        ):
            window_seconds = DEFAULT_WINDOW_SECONDS
        if (
            isinstance(max_requests, bool)
            or not isinstance(max_requests, int)
            or not 1 <= max_requests <= MAX_REQUESTS
        ):
            max_requests = DEFAULT_MAX_REQUESTS
        if (
            isinstance(max_clients, bool)
            or not isinstance(max_clients, int)
            or not 1 <= max_clients <= MAX_TRACKED_CLIENTS
        ):
            max_clients = MAX_TRACKED_CLIENTS
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self.max_clients = max_clients
        self._clock = clock
        self._salt = secrets.token_bytes(32)
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "AIRateLimiter":
        settings = os.environ if environ is None else environ
        return cls(
            window_seconds=_configuration_value(
                settings,
                "AI_RATE_LIMIT_WINDOW_SECONDS",
                DEFAULT_WINDOW_SECONDS,
                MAX_WINDOW_SECONDS,
            ),
            max_requests=_configuration_value(
                settings,
                "AI_RATE_LIMIT_MAX_REQUESTS",
                DEFAULT_MAX_REQUESTS,
                MAX_REQUESTS,
            ),
            clock=clock,
        )

    def _client_key(self, client_id: Optional[str]) -> str:
        identifier = str(client_id or "unknown")
        return hashlib.blake2b(
            identifier.encode("utf-8", errors="replace"),
            key=self._salt,
            digest_size=16,
        ).hexdigest()

    def _remove_expired(self, now: float) -> int:
        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= self.window_seconds
        ]
        for key in expired:
            del self._windows[key]
        return len(expired)

    def allow(self, client_id: Optional[str]) -> bool:
        """Record one request and report whether it is within the configured limit."""
        now = self._clock()
        client_key = self._client_key(client_id)

        with self._lock:
            self._remove_expired(now)
            window = self._windows.get(client_key)
            if window is None:
                if len(self._windows) >= self.max_clients:
                    return False
                self._windows[client_key] = _Window(now, 1)
                return True

            if window.request_count >= self.max_requests:
                return False
            window.request_count += 1
            return True

    def cleanup(self) -> int:
        """Remove expired clients and return the number of entries removed."""
        with self._lock:
            return self._remove_expired(self._clock())

    @property
    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._windows)
