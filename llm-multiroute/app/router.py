"""Multi-model routing.

Static routing: each business task (summarize, generate, extract, ...) has its own
model (MODEL_<TASK> env var) and system prompt.

Dynamic routing: /api/support first detects the customer's intent, then hands the
message to the specialist LLM for technical, billing or pre-sale support.
"""
import json
import logging
from typing import List, Optional

from app import config, llm_client
from app.logging_config import request_id_var
from app.schemas import TaskResponse
from app.tracing import observe, update_trace

logger = logging.getLogger("router")

SENTIMENT_LABELS = ["positive", "negative", "neutral"]
INTENT_LABELS = ["technical", "billing", "presales", "general"]
DEFAULT_CATEGORIES = [
    "technology", "business", "finance", "health", "sports", "entertainment", "politics", "other",
]

SYSTEM_PROMPTS = {
    "chat": "You are a helpful assistant. Answer clearly and concisely.",
    "summarize": (
        "You are a business analyst. Summarise the user's text in at most 3 short bullet points. "
        "Only use facts stated in the text; never add new information."
    ),
    "generate": (
        "You are a content-marketing copywriter. Write engaging, accurate marketing copy for the "
        "brief given by the user, in the requested tone. Keep it under 150 words."
    ),
    "extract": (
        "You are an insight-extraction engine. Read the user's text and return ONLY a JSON object "
        'with the keys "key_insights", "entities" and "action_items", each a list of strings.'
    ),
    "classify": (
        "You are a text classifier. Reply with exactly one category from this list and nothing "
        "else: {categories}."
    ),
    "sentiment": (
        "You are a sentiment classifier. Reply with exactly one word: positive, negative or neutral."
    ),
    "intent": (
        "You route customer-service messages. Reply with exactly one word from this list: "
        "technical (product problems, errors, how-to questions), "
        "billing (invoices, payments, refunds, charges), "
        "presales (pricing, plans, features or demos before buying), "
        "general (anything else)."
    ),
    "support_technical": (
        "You are a friendly technical-support engineer. Give clear, step-by-step troubleshooting help."
    ),
    "support_billing": (
        "You are a billing-support specialist. Help with invoices, payments and refunds. "
        "Never ask for full card numbers or passwords."
    ),
    "support_presales": (
        "You are a pre-sales consultant. Explain plans, features and pricing, and suggest a next "
        "step such as booking a demo."
    ),
    "support_general": "You are a customer-service agent. Help politely and briefly.",
}


def model_map() -> dict:
    """Which model each task is currently routed to."""
    return {task: config.model_for(task) for task in SYSTEM_PROMPTS}


def match_label(raw: str, labels: List[str], fallback: str) -> str:
    """Pick the label that appears first in the model's reply (small models are chatty)."""
    text = raw.lower()
    hits = [(text.find(label.lower()), label) for label in labels if label.lower() in text]
    return min(hits)[1] if hits else fallback


async def _run(
    task: str,
    user_content: str,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    json_mode: bool = False,
) -> llm_client.LLMResult:
    update_trace(metadata={"request_id": request_id_var.get()})
    messages = [
        {"role": "system", "content": system or SYSTEM_PROMPTS[task]},
        {"role": "user", "content": user_content},
    ]
    return await llm_client.chat(
        config.model_for(task), messages, temperature=temperature, json_mode=json_mode, task=task
    )


def _response(task: str, result: llm_client.LLMResult, **extra) -> TaskResponse:
    return TaskResponse(
        task=task,
        model=result.model,
        output=extra.pop("output", result.content),
        latency_ms=result.latency_ms,
        **extra,
    )


@observe(name="chat")
async def chat(message: str) -> TaskResponse:
    return _response("chat", await _run("chat", message))


@observe(name="summarize")
async def summarize(text: str) -> TaskResponse:
    return _response("summarize", await _run("summarize", text, temperature=0.2))


@observe(name="generate")
async def generate(prompt: str, tone: str) -> TaskResponse:
    result = await _run("generate", f"Tone: {tone}\nBrief: {prompt}", temperature=0.8)
    return _response("generate", result)


@observe(name="extract")
async def extract(text: str) -> TaskResponse:
    result = await _run("extract", text, temperature=0, json_mode=True)
    try:
        output = json.dumps(json.loads(result.content), indent=2)
    except json.JSONDecodeError:
        output = result.content
    return _response("extract", result, output=output)


@observe(name="classify")
async def classify(text: str, categories: Optional[List[str]] = None) -> TaskResponse:
    cats = [c.strip().lower() for c in (categories or DEFAULT_CATEGORIES) if c.strip()]
    system = SYSTEM_PROMPTS["classify"].format(categories=", ".join(cats))
    result = await _run("classify", text, system=system, temperature=0)
    label = match_label(result.content, cats, fallback="other" if "other" in cats else cats[-1])
    return _response("classify", result, output=label, label=label)


@observe(name="sentiment")
async def sentiment(text: str) -> TaskResponse:
    result = await _run("sentiment", text, temperature=0)
    label = match_label(result.content, SENTIMENT_LABELS, fallback="neutral")
    return _response("sentiment", result, output=label, label=label)


@observe(name="intent")
async def intent(text: str) -> TaskResponse:
    result = await _run("intent", text, temperature=0)
    label = match_label(result.content, INTENT_LABELS, fallback="general")
    return _response("intent", result, output=label, label=label)


@observe(name="support")
async def support(
    message: str, session_id: Optional[str] = None, user_id: Optional[str] = None
) -> TaskResponse:
    """Dynamic routing layer: detect intent, then call the specialist LLM."""
    detected = await intent(message)
    route = f"support_{detected.label}"
    logger.info("support_routed", extra={"intent": detected.label, "routed_to": route})
    # session_id groups a conversation in Langfuse > Sessions; user_id feeds Langfuse > Users.
    update_trace(session_id=session_id, user_id=user_id, tags=["support", route])
    result = await _run(route, message, temperature=0.4)
    return TaskResponse(
        task="support",
        model=result.model,
        output=result.content,
        label=detected.label,
        routed_to=route,
        latency_ms=detected.latency_ms + result.latency_ms,
    )
