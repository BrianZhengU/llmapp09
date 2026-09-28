import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from api_client import call
from metrics import ExactLabelMatch

CASES = [
    ("I was charged twice for my subscription this month.", "billing"),
    ("Can I get a refund for last month's invoice?", "billing"),
    ("The app crashes with error 500 every time I upload a file.", "technical"),
    ("How do I reset my password? The reset email never arrives.", "technical"),
    ("What does the enterprise plan cost and can I book a demo?", "presales"),
    ("Do you offer a discount for non-profits before we sign up?", "presales"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_intent(text, expected):
    result = call("intent", {"text": text})
    test_case = LLMTestCase(input=text, actual_output=result["output"], expected_output=expected)
    assert_test(test_case, [ExactLabelMatch()])


@pytest.mark.parametrize("text,expected", CASES[:3:2])
def test_support_routing(text, expected):
    """The dynamic routing layer must send the message to the matching specialist."""
    result = call("support", {"message": text})
    assert result["routed_to"] == f"support_{expected}"
