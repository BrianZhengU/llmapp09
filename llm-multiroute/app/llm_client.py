"""Async LLM client: Ollama (local or cloud) by default, OpenAI for models named "openai/<model>".

Every call is logged and recorded as a Langfuse *generation* (model, input, output, tokens).
"""
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import httpx

from app import config
from app.logging_config import LOG_PROMPTS
from app.tracing import observe, update_generation

logger = logging.getLogger("llm")


class LLMError(RuntimeError):
    """Raised when the LLM backend cannot be reached or returns an error."""


@dataclass
class LLMResult:
    content: str
    model: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


async def _call_ollama(
    model: str, messages: List[Dict[str, str]], temperature: Optional[float], json_mode: bool
) -> Tuple[str, Optional[int], Optional[int]]:
    headers = {"Authorization": f"Bearer {config.OLLAMA_API_KEY}"} if config.OLLAMA_API_KEY else {}
    payload: dict = {"model": model, "messages": messages, "stream": False}
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    if json_mode:
        payload["format"] = "json"
    async with httpx.AsyncClient(base_url=config.OLLAMA_BASE_URL, timeout=config.LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post("/api/chat", json=payload, headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return (
        data.get("message", {}).get("content", "").strip(),
        data.get("prompt_eval_count"),
        data.get("eval_count"),
    )


async def _call_openai(
    model: str, messages: List[Dict[str, str]], temperature: Optional[float], json_mode: bool
) -> Tuple[str, Optional[int], Optional[int]]:
    if not config.OPENAI_API_KEY:
        raise LLMError(f"Model '{model}' needs OPENAI_API_KEY to be set")
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(base_url=config.OPENAI_BASE_URL, timeout=config.LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            "/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        )
        resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage") or {}
    return (
        (data["choices"][0]["message"].get("content") or "").strip(),
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
    )


@observe(name="llm-call", as_type="generation", capture_input=False, capture_output=False)
async def chat(
    model: str,
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
    json_mode: bool = False,
    task: str = "-",
) -> LLMResult:
    provider, _, name = model.partition("/") if model.startswith("openai/") else ("ollama", "", model)
    call = _call_openai if provider == "openai" else _call_ollama
    update_generation(
        name=f"llm-call:{task}",
        model=name,
        input=messages,
        model_parameters={"temperature": temperature, "json_mode": json_mode},
        metadata={"task": task, "provider": provider},
    )

    start = time.perf_counter()
    try:
        content, prompt_tokens, completion_tokens = await call(name, messages, temperature, json_mode)
    except httpx.HTTPStatusError as exc:
        message = f"LLM backend returned {exc.response.status_code}: {exc.response.text[:300]}"
        logger.error(
            "llm_call_failed",
            extra={"task": task, "model": model, "status_code": exc.response.status_code,
                   "latency_ms": int((time.perf_counter() - start) * 1000)},
        )
        update_generation(level="ERROR", status_message=message)
        raise LLMError(message) from exc
    except httpx.HTTPError as exc:
        message = f"Could not reach the {provider} LLM backend: {exc}"
        logger.error("llm_unreachable", extra={"task": task, "model": model, "error": str(exc)})
        update_generation(level="ERROR", status_message=message)
        raise LLMError(message) from exc

    result = LLMResult(
        content=content,
        model=model,
        latency_ms=int((time.perf_counter() - start) * 1000),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    update_generation(
        output=content,
        usage_details={"input": prompt_tokens or 0, "output": completion_tokens or 0},
    )
    log_fields = {
        "task": task,
        "model": model,
        "latency_ms": result.latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "prompt_chars": sum(len(m["content"]) for m in messages),
        "output_chars": len(content),
    }
    if LOG_PROMPTS:
        log_fields.update(prompt=messages[-1]["content"], output=content)
    logger.info("llm_call", extra=log_fields)
    return result
