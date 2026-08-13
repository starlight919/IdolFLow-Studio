"""Simple TTL cache for file-system scans and expensive lookups."""

from __future__ import annotations

import time
import threading
from collections import OrderedDict


MAX_ENTRIES = 64
DEFAULT_TTL = 5.0  # seconds


class TTLCache:
    """Thread-safe, bounded in-memory TTL cache that evicts LRU entries."""

    def __init__(self, max_entries: int = MAX_ENTRIES, default_ttl: float = DEFAULT_TTL):
        self._max = max_entries
        self._ttl = default_ttl
        self._lock = threading.RLock()
        self._store: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires, value = entry
            if time.monotonic() > expires:
                del self._store[key]
                return None
            # LRU: move to end
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: object, ttl: float | None = None):
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (time.monotonic() + (ttl if ttl is not None else self._ttl), value)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def invalidate(self, key: str | None = None):
        """Remove a single key, or all keys if *key* is None."""
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


# Module-level singleton
_directory_cache = TTLCache(max_entries=32, default_ttl=5.0)


def cached_list_dir(directory: str):
    """Return a cached directory listing (as a list of paths)."""
    from pathlib import Path
    key = f"list::{directory}"
    result = _directory_cache.get(key)
    if result is not None:
        return result
    items = [p.as_posix() for p in sorted(Path(directory).iterdir()) if not p.name.startswith(".")]
    _directory_cache.set(key, items)
    return items
