"""Input and output guardrails.

Input  (before any LLM call):
  1. length limit
  2. prompt-injection / jailbreak patterns          -> block
  3. harmful-request patterns                       -> block
  4. PII: email, SG NRIC/FIN, phone, card numbers   -> redact (or block / off)
  5. optional LLM safety classifier (Llama Guard)   -> block if "unsafe"
Output (before returning to the user):
  1. PII redaction
  2. system-prompt leakage                          -> replace with a refusal

Pattern lists are deliberately small and readable: they are a teaching baseline,
not a complete defence. Layer them with model-based checks in production.
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional, Sequence

from app import llm_client
from app.router import SYSTEM_PROMPTS
from app.schemas import TaskResponse
from app.tracing import observe, update_trace

logger = logging.getLogger("guardrails")

MAX_INPUT_CHARS = int(os.getenv("GUARDRAIL_MAX_INPUT_CHARS", "8000"))
PII_MODE = os.getenv("GUARDRAIL_PII_MODE", "redact").lower()  # redact | block | off
# e.g. llama-guard3:1b (ollama pull llama-guard3:1b). Empty = disabled.
GUARD_MODEL = os.getenv("GUARDRAIL_LLM_MODEL", "")

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|your)\b.{0,20}\b(instructions?|prompts?|rules|guidelines)\b",
    r"\b(reveal|show|print|repeat|output|leak|display)\b.{0,40}\b(system|hidden|initial|original)\s+(prompt|instructions?|message)",
    r"\byou are now\b.{0,20}\b(dan|unfiltered|jailbroken|uncensored|in developer mode)\b",
    r"\b(jailbreak|developer mode|do anything now)\b",
    r"\bpretend\b.{0,30}\bno (rules|restrictions|guidelines|filters)\b",
    r"</?\s*(system|assistant)\s*>|\[/?INST\]|<\|im_start\|>",  # role-tag smuggling
]

HARMFUL_PATTERNS = {
    "weapons": r"\b(make|build|assemble|synthesi[sz]e)\b.{0,40}\b(bomb|explosives?|nerve agent|chemical weapon)\b",
    "malware": r"\b(write|create|build|code)\b.{0,40}\b(ransomware|keylogger|malware|computer virus|botnet)\b",
    "self_harm": r"\b(how (do i|to|can i)|best way to)\b.{0,20}\b(kill|hurt|harm) myself\b",
}

SELF_HARM_MESSAGE = (
    "It sounds like you may be going through a difficult time. You don't have to face it alone: "
    "in Singapore you can call SOS at 1767 (24 hours) or text 9151 1767."
)

# Order matters: card numbers before phone numbers so 16 digits are not read as a phone.
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "nric": re.compile(r"\b[STFGM]\d{7}[A-Z]\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    # SG numbers (+65 optional) not embedded in a longer digit group, or any +<country> number.
    "phone": re.compile(
        r"(?<![\d.])(?<![\d.][ -])(?:\+65[\s-]?)?[689]\d{3}[\s-]?\d{4}(?![\s-]?\d)"
        r"|\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}"
    ),
}

_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
_HARMFUL_RE = {name: re.compile(p, re.IGNORECASE) for name, p in HARMFUL_PATTERNS.items()}
# Fingerprints of our own system prompts, used to catch prompt leakage in outputs.
_PROMPT_FINGERPRINTS = [p[:60].lower() for p in SYSTEM_PROMPTS.values() if len(p) >= 30]


@dataclass
class Verdict:
    allowed: bool
    text: str
    reasons: List[str] = field(default_factory=list)  # why it was blocked
    notes: List[str] = field(default_factory=list)  # non-blocking actions, e.g. pii_redacted:email
    message: Optional[str] = None


class GuardrailBlocked(Exception):
    def __init__(self, stage: str, reasons: List[str], message: Optional[str] = None):
        super().__init__(f"{stage} blocked: {reasons}")
        self.stage, self.reasons, self.message = stage, reasons, message


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def redact_pii(text: str) -> "tuple[str, List[str]]":
    """Replace PII with [REDACTED_<TYPE>]; return the new text and the PII types found."""
    found: List[str] = []

    def replacer(kind: str):
        def _sub(match: re.Match) -> str:
            if kind == "credit_card" and not _luhn_ok(re.sub(r"\D", "", match.group())):
                return match.group()  # a long number, but not a card number
            found.append(kind)
            return f"[REDACTED_{kind.upper()}]"
        return _sub

    for kind, pattern in PII_PATTERNS.items():
        text = pattern.sub(replacer(kind), text)
    return text, sorted(set(found))


def scan_input(text: str) -> Verdict:
    """Rule-based input checks (no LLM call)."""
    if len(text) > MAX_INPUT_CHARS:
        return Verdict(False, text, [f"input_too_long:{len(text)}>{MAX_INPUT_CHARS}"])
    if any(p.search(text) for p in _INJECTION_RE):
        return Verdict(False, text, ["prompt_injection"])
    for name, pattern in _HARMFUL_RE.items():
        if pattern.search(text):
            message = SELF_HARM_MESSAGE if name == "self_harm" else None
            return Verdict(False, text, [f"harmful:{name}"], message=message)

    if PII_MODE == "off":
        return Verdict(True, text)
    redacted, pii = redact_pii(text)
    if pii and PII_MODE == "block":
        return Verdict(False, text, [f"pii:{kind}" for kind in pii])
    return Verdict(True, redacted, notes=[f"pii_redacted:{kind}" for kind in pii])


async def llm_safety_check(text: str) -> Optional[str]:
    """Ask Llama Guard whether the input is safe. Returns the unsafe category, or None if safe."""
    result = await llm_client.chat(
        GUARD_MODEL, [{"role": "user", "content": text}], temperature=0, task="guardrail"
    )
    verdict = result.content.strip().lower()
    if verdict.startswith("unsafe"):
        lines = verdict.splitlines()
        return lines[1].strip() if len(lines) > 1 else "unsafe"
    return None


@observe(name="input-guardrail")
async def check_input(text: str) -> Verdict:
    verdict = scan_input(text)
    if verdict.allowed and GUARD_MODEL:
        # Fail closed: if the safety model errors, LLMError propagates and the request fails.
        category = await llm_safety_check(verdict.text)
        if category:
            verdict = Verdict(False, text, [f"llm_guard:{category}"])
    return verdict


@observe(name="output-guardrail")
def check_output(text: str) -> Verdict:
    lowered = text.lower()
    if any(fp in lowered for fp in _PROMPT_FINGERPRINTS):
        return Verdict(True, "Sorry, I can't share that.", notes=["output_blocked:system_prompt_leak"])
    if PII_MODE == "off":
        return Verdict(True, text)
    redacted, pii = redact_pii(text)
    return Verdict(True, redacted, notes=[f"output_pii_redacted:{kind}" for kind in pii])


@observe(name="guarded-request")
async def guarded(
    task: str,
    user_text: str,
    call: Callable[[str], Awaitable[TaskResponse]],
    also_check: Sequence[str] = (),
) -> TaskResponse:
    """Run input guardrails -> the LLM task (on the sanitised text) -> output guardrails.

    also_check: other user-supplied fields that end up in the prompt (tone, categories).
    They are scanned for injection/harmful content but passed through unchanged.
    """
    update_trace(name=task)
    verdict = await check_input(user_text)
    for extra in also_check:
        if not verdict.allowed:
            break
        extra_verdict = scan_input(extra)
        if not extra_verdict.allowed:
            verdict = extra_verdict
    if not verdict.allowed:
        logger.warning("guardrail_blocked", extra={"stage": "input", "task": task, "reasons": verdict.reasons})
        update_trace(tags=["guardrail:blocked"])
        raise GuardrailBlocked("input", verdict.reasons, verdict.message)

    response = await call(verdict.text)
    out = check_output(response.output)
    response.output = out.text
    notes = verdict.notes + out.notes
    if notes:
        logger.info("guardrail_actions", extra={"task": task, "actions": notes})
        update_trace(tags=[f"guardrail:{n}" for n in notes])
    response.guardrails = notes or None
    return response
