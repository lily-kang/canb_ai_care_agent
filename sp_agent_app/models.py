from typing import List, Dict, Any, Literal

from datetime import datetime
from pydantic import BaseModel


class CounselRequest(BaseModel):
    """Single-student counseling request payload."""

    member_code: str
    exam_test_code: str
    learning_period_start: str
    learning_period_end: str
    exam_div: str
    exam_name: str

    # Optional per-student JSON payload (example.json 의 students[member_code] 한 건 분)
    student_payload: Dict[str, Any] | None = None







class BatchCounselItemV2(BaseModel):
    """
    External batch payload item.
    """

    member_code: str
    exam_test_code: str
    exam_div: str
    exam_name: str
    course_code: int | None = None
    student_performance: Dict[str, Any]


class BatchCounselPayloadV2(BaseModel):
    """External batch counseling payload."""

    batch_data: List[BatchCounselItemV2]


class CounselResult(BaseModel):
    """Result for a single counseling run."""
    exam_test_code: str
    member_code: str
    course_code: int | None = None
    exam_div: str | None = None
    exam_name: str | None = None
    status: Literal["success", "error"]
    
    # 최종 상담 가이드 결과를 JSON 객체(dict)로 전달
    analysis_result: Dict[str, Any] | None = None
    error: str | None = None



class BatchCounselResponse(BaseModel):
    """Aggregated result for a batch counseling run."""

    total: int
    results: List[CounselResult]

