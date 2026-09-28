"""Custom deterministic DeepEval metric (no judge LLM needed)."""
import string

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


def _normalize(text: str) -> str:
    return (text or "").strip().lower().strip(string.punctuation + " ")


class ExactLabelMatch(BaseMetric):
    """Score 1.0 when actual_output equals expected_output (case/punctuation-insensitive)."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        actual, expected = _normalize(test_case.actual_output), _normalize(test_case.expected_output)
        self.score = 1.0 if actual == expected else 0.0
        self.success = self.score >= self.threshold
        self.reason = f"expected '{expected}', got '{actual}'"
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Exact Label Match"
