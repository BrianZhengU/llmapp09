"""Helper for calling the LLM Multi-Route API from the tests."""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080").rstrip("/")
TIMEOUT = float(os.getenv("API_TIMEOUT_SECONDS", "180"))


def call(task: str, payload: dict) -> dict:
    """POST to /api/<task> and return the JSON body (raises on HTTP errors)."""
    resp = requests.post(f"{API_BASE_URL}/api/{task}", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()
