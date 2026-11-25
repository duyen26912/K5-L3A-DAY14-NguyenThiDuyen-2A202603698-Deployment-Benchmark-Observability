"""Redis-backed daily cost guard."""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"llm-cost:daily:{day}"


def check_budget() -> None:
    try:
        total = float(r.get(_daily_key()) or 0.0)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost storage unavailable") from exc
    if total >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (
        max(0, input_tokens) / 1000 * PRICE_INPUT_PER_1K
        + max(0, output_tokens) / 1000 * PRICE_OUTPUT_PER_1K
    )
    key = _daily_key()
    try:
        r.incrbyfloat(key, cost)
        r.expire(key, 60 * 60 * 24 * 2)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost storage unavailable") from exc
    return cost
