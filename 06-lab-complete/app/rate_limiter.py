"""Redis-backed sliding-window rate limiter shared by workers and instances."""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

_CHECK_AND_ADD = r"""
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry_ms = window_ms
  if oldest[2] then retry_ms = tonumber(oldest[2]) + window_ms - now_ms end
  return {0, math.max(1, math.ceil(retry_ms / 1000))}
end
redis.call('ZADD', key, now_ms, member)
redis.call('EXPIRE', key, math.ceil(window_ms / 1000) + 1)
return {1, 0}
"""


def check_rate_limit(key: str) -> None:
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    redis_key = f"rate-limit:{key_hash}"
    now_ms = int(time.time() * 1000)
    try:
        allowed, retry_after = r.eval(
            _CHECK_AND_ADD,
            1,
            redis_key,
            now_ms,
            60_000,
            settings.rate_limit_per_minute,
            f"{now_ms}:{uuid.uuid4().hex}",
        )
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limit storage unavailable") from exc

    if not int(allowed):
        retry_after = max(1, int(retry_after))
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
