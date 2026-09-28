import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from api_client import call
from metrics import ExactLabelMatch

CASES = [
    ("Absolutely love this product, it works perfectly!", "positive"),
    ("Support solved my issue in five minutes. Great service.", "positive"),
    ("The delivery was two weeks late and nobody answered my calls.", "negative"),
    ("The app keeps crashing and I lost all my notes. Very disappointed.", "negative"),
    ("The package arrived on Tuesday.", "neutral"),
    ("Our office is on the third floor.", "neutral"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_sentiment(text, expected):
    result = call("sentiment", {"text": text})
    test_case = LLMTestCase(input=text, actual_output=result["output"], expected_output=expected)
    assert_test(test_case, [ExactLabelMatch()])
