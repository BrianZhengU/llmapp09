"""Unit-test setup: no network. llm_client.chat is replaced by a fake LLM."""
import os
import sys
import tempfile

# Must be set before the app is imported.
os.environ["OLLAMA_BASE_URL"] = "http://llm.invalid"
os.environ["LOG_DIR"] = tempfile.mkdtemp()
for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "GUARDRAIL_LLM_MODEL"):
    os.environ.pop(key, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import llm_client  # noqa: E402
from app.main import app  # noqa: E402


class FakeLLM:
    """Answers like a well-behaved model, and records every prompt it receives."""

    def __init__(self):
        self.calls = []
        self.reply = None  # set to force a specific reply

    async def __call__(self, model, messages, temperature=None, json_mode=False, task="-"):
        self.calls.append({"task": task, "messages": messages})
        system, user = messages[0]["content"].lower(), messages[-1]["content"].lower()
        if self.reply is not None:
            content = self.reply
        elif task == "sentiment":
            content = "Negative" if "late" in user else "positive"
        elif task == "intent":
            content = "billing" if ("charged" in user or "invoice" in user) else "technical"
        elif task == "extract":
            content = '{"key_insights": [], "entities": [], "action_items": []}'
        else:
            content = f"answer for {task}"
        return llm_client.LLMResult(content=content, model=model, latency_ms=1)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm_client, "chat", fake)
    return fake


@pytest.fixture
def client(fake_llm):
    with TestClient(app) as c:
        yield c
