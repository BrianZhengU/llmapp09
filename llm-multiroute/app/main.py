"""LLM Multi-Route API.

Run:  python -m uvicorn app.main:app --port 8080 --reload
Docs: http://localhost:8080/swagger-ui.html
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import router, tracing
from app.guardrails import GuardrailBlocked, guarded
from app.llm_client import LLMError
from app.logging_config import request_id_var, setup_logging
from app.schemas import (
    ChatRequest,
    ClassifyRequest,
    GenerateRequest,
    SupportRequest,
    TaskResponse,
    TextRequest,
)

setup_logging()
logger = logging.getLogger("api")



@asynccontextmanager
async def lifespan(_app: FastAPI):
    tracing.check_connection()
    yield
    tracing.flush()


app = FastAPI(
    lifespan=lifespan,
    title="LLM Multi-Route API",
    version="1.0.0",
    docs_url="/swagger-ui.html",
    redoc_url=None,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Assign a request id (or reuse X-Request-ID), log method/path/status/latency."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error", extra={"method": request.method, "path": request.url.path})
        raise
    finally:
        request_id_var.reset(token)
    latency_ms = int((time.perf_counter() - start) * 1000)
    if request.url.path != "/health":  # keep k8s probes out of the logs
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "client_ip": request.client.host if request.client else None,
                "request_id": request_id,
            },
        )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(GuardrailBlocked)
async def guardrail_handler(request: Request, exc: GuardrailBlocked):
    detail = {"error": "blocked_by_guardrail", "stage": exc.stage, "reasons": exc.reasons}
    if exc.message:
        detail["message"] = exc.message
    return JSONResponse(status_code=400, content={"detail": detail})


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    logger.error("llm_error", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/swagger-ui.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/models")
def models():
    """Current task -> model routing table."""
    return router.model_map()


@app.post("/api/chat", response_model=TaskResponse)
async def chat(req: ChatRequest):
    return await guarded("chat", req.message, router.chat)


@app.post("/api/summarize", response_model=TaskResponse, tags=["Business Analysis"])
async def summarize(req: TextRequest):
    return await guarded("summarize", req.text, router.summarize)


@app.post("/api/generate", response_model=TaskResponse, tags=["Content Marketing"])
async def generate(req: GenerateRequest):
    return await guarded(
        "generate", req.prompt, lambda text: router.generate(text, req.tone), also_check=[req.tone]
    )


@app.post("/api/extract", response_model=TaskResponse, tags=["Content Marketing"])
async def extract(req: TextRequest):
    return await guarded("extract", req.text, router.extract)


@app.post("/api/classify", response_model=TaskResponse, tags=["Classification"])
async def classify(req: ClassifyRequest):
    return await guarded(
        "classify",
        req.text,
        lambda text: router.classify(text, req.categories),
        also_check=req.categories or [],
    )


@app.post("/api/sentiment", response_model=TaskResponse, tags=["Classification"])
async def sentiment(req: TextRequest):
    return await guarded("sentiment", req.text, router.sentiment)


@app.post("/api/intent", response_model=TaskResponse, tags=["Classification"])
async def intent(req: TextRequest):
    return await guarded("intent", req.text, router.intent)


@app.post("/api/support", response_model=TaskResponse, tags=["Customer Service"])
async def support(req: SupportRequest):
    return await guarded(
        "support",
        req.message,
        lambda text: router.support(text, session_id=req.session_id, user_id=req.user_id),
    )
