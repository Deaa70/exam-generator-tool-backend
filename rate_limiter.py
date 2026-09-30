import time
from collections import defaultdict

# Maps a client key (e.g. IP address) to the timestamps of its recent requests.
_hits: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """Return True if a request from `key` is allowed, False if the limit is exceeded."""
    now = time.time()

    # Keep only the hits that are still inside the time window.
    recent = [t for t in _hits[key] if now - t < window_seconds]
    _hits[key] = recent

    if len(recent) >= max_requests:
        return False

    recent.append(now)
    return True