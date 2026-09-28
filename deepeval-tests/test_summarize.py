"""Summarization quality, judged by an LLM (OPENAI_API_KEY or `deepeval set-ollama`)."""
import pytest
from deepeval import assert_test
from deepeval.metrics import GEval, HallucinationMetric
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from api_client import call

DOCUMENTS = [
    (
        "Acme Corp reported third-quarter revenue of $4.2 million, up 12% year on year, driven mainly by "
        "enterprise renewals in Southeast Asia. Operating costs rose 5% because of new hiring in the "
        "engineering team. Churn among small-business customers increased slightly to 3.1%. Management "
        "expects fourth-quarter growth to remain above 10% and plans to launch two AI features in January."
    ),
    (
        "The city council approved a plan to add 40 km of protected bicycle lanes by 2028. The project "
        "will cost $85 million, funded by a transport levy. Critics argue it will reduce parking spaces "
        "downtown, while supporters cite a 30% rise in cycling commuters since 2022."
    ),
]


def summary_quality() -> GEval:
    # Built inside the test: creating a judged metric needs the judge configured.
    return GEval(
        name="Summary Quality",
        criteria=(
            "The actual output is a concise summary of the input: it is clearly shorter than the "
            "input, covers the most important facts and numbers, and contains no information "
            "absent from the input."
        ),
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        threshold=0.6,
    )


@pytest.mark.parametrize("document", DOCUMENTS)
def test_summarize(document):
    summary = call("summarize", {"text": document})["output"]
    assert len(summary) < len(document), "summary is not shorter than the input"

    test_case = LLMTestCase(input=document, actual_output=summary, context=[document])
    assert_test(test_case, [summary_quality(), HallucinationMetric(threshold=0.5)])
