"""Application settings, read from environment variables (and an optional .env file)."""
import os

from dotenv import load_dotenv

load_dotenv()

# Ollama endpoint. Cloud: https://ollama.com (needs OLLAMA_API_KEY). Local: http://localhost:11434
OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "https://ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# Model used for any task without its own MODEL_<TASK> override.
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL") or "gpt-oss:20b"

# Optional: route a task to OpenAI by naming its model "openai/<model>", e.g.
# MODEL_GENERATE=openai/gpt-4o-mini
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))


def model_for(task: str) -> str:
    """Return the model routed to a task, e.g. MODEL_SUMMARIZE or MODEL_SUPPORT_BILLING."""
    return os.getenv(f"MODEL_{task.upper()}") or DEFAULT_MODEL
