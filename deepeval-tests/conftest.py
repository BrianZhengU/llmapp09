import pytest
import requests

from api_client import API_BASE_URL


@pytest.fixture(scope="session", autouse=True)
def backend_is_up():
    """Fail fast with a clear message if the API is not running."""
    try:
        requests.get(f"{API_BASE_URL}/health", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        pytest.exit(f"LLM API not reachable at {API_BASE_URL} ({exc}). Start llm-multiroute first.", returncode=1)
