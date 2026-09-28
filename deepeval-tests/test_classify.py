import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from api_client import call
from metrics import ExactLabelMatch

# (text, categories or None for the API defaults, expected label)
CASES = [
    ("Nvidia announced a new GPU architecture for training AI models.", None, "technology"),
    ("The central bank raised interest rates by 25 basis points.", None, "finance"),
    ("A new study links daily walking to lower blood pressure.", None, "health"),
    ("Singapore won gold in the 4x100m relay at the SEA Games.", ["technology", "business", "sports"], "sports"),
    ("The startup closed a $20M Series B round led by Sequoia.", ["technology", "business", "sports"], "business"),
]


@pytest.mark.parametrize("text,categories,expected", CASES)
def test_classify(text, categories, expected):
    result = call("classify", {"text": text, "categories": categories})
    test_case = LLMTestCase(input=text, actual_output=result["output"], expected_output=expected)
    assert_test(test_case, [ExactLabelMatch()])
