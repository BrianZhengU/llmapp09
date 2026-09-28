from typing import List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Annotated

ShortStr = Annotated[str, Field(max_length=40)]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["What is LLMOps in one paragraph?"])


class TextRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        examples=["Q3 revenue grew 12% to $4.2M, driven by enterprise renewals. Churn rose slightly in SMB."],
    )


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, examples=["Launch announcement for our new AI-powered note-taking app"])
    tone: ShortStr = Field("professional", examples=["professional", "playful", "formal"])


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=["Apple unveiled a new M-series chip for its laptops."])
    categories: Optional[List[ShortStr]] = Field(
        None, max_length=20, examples=[["technology", "business", "sports"]]
    )


class SupportRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["I was charged twice for my subscription this month."])
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class TaskResponse(BaseModel):
    task: str
    model: str
    output: str
    label: Optional[str] = None
    routed_to: Optional[str] = None
    latency_ms: int
    guardrails: Optional[List[str]] = None  # actions taken, e.g. pii_redacted:email
