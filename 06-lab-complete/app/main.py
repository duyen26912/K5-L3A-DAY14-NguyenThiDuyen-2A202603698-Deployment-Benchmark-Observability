"""Production-ready FastAPI agent for the Day 14 final project."""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Serialize each application log record as one valid JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for name in ("event", "path", "method", "status", "duration_ms", "cost_usd"):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


logger = logging.getLogger("production_agent")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    stream = logging.StreamHandler()
    stream.setFormatter(JsonFormatter())
    logger.addHandler(stream)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Agent startup", extra={"event": "startup"})
    yield
    logger.info("Agent shutdown complete", extra={"event": "shutdown"})


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.middleware("http")
async def log_requests(request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        logger.info(
            "HTTP request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )


@app.get("/health")
def health():
    """Liveness is independent of Redis availability."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness requires the shared Redis backend to be reachable."""
    if not redis_healthy():
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Redis is not available")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    cost = record_cost(len(body.question.split()), len(answer.split()))
    logger.info(
        "Agent request completed",
        extra={"event": "agent_response", "cost_usd": cost},
    )
    return {"question": body.question, "answer": answer}
