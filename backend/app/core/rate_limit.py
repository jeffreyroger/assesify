import time
import threading
from flask import request

# Simple in-memory rate limiter: per-key (IP+endpoint) sliding window timestamps
_WINDOW = 60  # seconds

_lock = threading.Lock()
_counters = {}


def check_rate_limit(key: str, limit: int = 60) -> bool:
    """Return True if under limit, False if rate limit exceeded.

    key should be something like f"auth:{ip}".
    """
    now = time.time()
    with _lock:
        slots = _counters.get(key, [])
        # keep only timestamps in window
        slots = [t for t in slots if now - t < _WINDOW]
        if len(slots) >= limit:
            _counters[key] = slots
            return False
        slots.append(now)
        _counters[key] = slots
        return True


def ratelimit_for_auth(limit: int = 60):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown')
            key = f"auth:{ip}:{request.path}"
            if not check_rate_limit(key, limit=limit):
                from flask import jsonify
                return jsonify({"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests", "details": {}}}), 429
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator
