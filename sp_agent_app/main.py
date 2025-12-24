import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from sp_agent.agent import root_agent
from sp_agent.mapping import build_feature_json_from_analytics
from sp_agent_app.config import get_settings
from sp_agent_app.models import (
    CounselResult,
    BatchCounselResponse,
    BatchCounselPayloadV2,
    BatchCounselItemV2,
)

from dotenv import load_dotenv
load_dotenv()



logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="CANB Counselor API")

# In-process session service and runner for the root_agent.
_session_service = InMemorySessionService()
_runner = Runner(
    app_name="sp_agent_app",
    agent=root_agent,
    session_service=_session_service,
)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Simple health check endpoint for liveness/readiness probes.
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "app": "CANB Counselor API",
    }


async def run_root_agent_once(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the full counseling pipeline once using ADK Runner.

    - Creates a fresh in-memory session with the given initial state.
    - Runs root_agent via Runner.run_async.
    - Reads `generated_counseling_guide` from the final session.state.
    """
    # Use member_code as user_id when available for easier debugging.
    user_id = str(state.get("member_code") or "anonymous")

    # 1) initial state로 세션 만들기
    session = await _runner.session_service.create_session(
        app_name=_runner.app_name,
        user_id=user_id,
        state=state,
    )

    # 2) Build a minimal user message; most logic relies on session.state.
    new_message = types.Content(
        parts=[types.Part.from_text(text="Run CANB counseling pipeline.")],
    )

    # 3) agent 실행하고 이벤트 처리 (side effects go into session.state)
    async for _ in _runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=new_message,
    ):
        # 이벤트 개별적으로 처리할 필요 없음; state는 세션에 저장됨
        pass

    # 4) Read final session state
    final_session = await _runner.session_service.get_session(
        app_name=_runner.app_name,
        user_id=session.user_id,
        session_id=session.id,
    )
    if not final_session:
        raise RuntimeError("Session not found after root_agent run")

    guide = final_session.state.get("generated_counseling_guide")
    if guide is None:
        raise RuntimeError("generated_counseling_guide not found in session state")

    return guide


def _chunked(sequence, size: int):
    """
    Yield successive chunks from the given sequence.
    simple helper to process large batches in smaller logical chunks
    (e.g., 20 at a time) while preserving overall ordering.
    """
    if size <= 0:
        # Fallback to processing everything in one chunk if misconfigured.
        yield sequence
        return

    for i in range(0, len(sequence), size):
        yield sequence[i : i + size]



@app.post("/counsel", response_model=CounselResult)
async def counsel(req: BatchCounselItemV2) -> CounselResult:
    """
    Run the counseling pipeline for a single student.

    V2 behavior:
      - Accepts a single item of /batch-counsel (BatchCounselItemV2).
      - Splits student_performance into raw_json/feature_json and injects them
        into ADK session state, then runs the root agent once.
    """
    state = _split_and_build_state_from_v2_item(req)
    try:
        guide = await run_root_agent_once(state)

        return CounselResult(
            member_code=str(state.get("member_code") or ""),
            exam_test_code=str(state.get("exam_test_code") or ""),
            status="success",
            analysis_result=guide,
            exam_div=str(state.get("exam_div") or ""),
            exam_name=str(state.get("exam_name") or ""),
            course_code=state.get("course_code") if state.get("course_code") is not None else None,
        )
    except Exception as e:
        logger.exception("Failed to run counseling pipeline for %s", state.get("member_code"))

        return CounselResult(
            member_code=str(state.get("member_code") or ""),
            exam_test_code=str(state.get("exam_test_code") or ""),
            status="error",
            analysis_result=None,
            error=str(e),
            exam_div=str(state.get("exam_div") or ""),
            exam_name=str(state.get("exam_name") or ""),
            course_code=state.get("course_code") if state.get("course_code") is not None else None,
        )


def _split_and_build_state_from_v2_item(item: BatchCounselItemV2) -> Dict[str, Any]:
    """
    Build initial ADK session state for a single student from BatchCounselItemV2.
    초기 ADK 세션 상태 만들기
    
    Split rule (as agreed):
      - raw_json    =  student_performance fields
      - feature_json = score=score_analysis,
                        routine=learning_routine,
                        attendance=attendance
                      
    """
    member_code = str(item.member_code)
    exam_test_code = str(item.exam_test_code)
    exam_div = str(item.exam_div)
    exam_name = str(item.exam_name)
    course_code = int(item.course_code) if item.course_code is not None else None

    perf = item.student_performance or {}
    score_analysis = perf.get("score_analysis") or {}
    learning_routine = perf.get("learning_routine") or {}
    attendance = perf.get("attendance") or {}

    # learning_period comes from score_analysis.analysis_period (primary source).
    analysis_period = {}
    if isinstance(score_analysis, dict):
        analysis_period = score_analysis.get("analysis_period") or {}
    learning_period_start = str((analysis_period or {}).get("start") or "")
    learning_period_end = str((analysis_period or {}).get("end") or "")

    # raw_json: everything except analytics blocks
    raw_json: Dict[str, Any] = {}
    if isinstance(perf, dict):
        for k, v in perf.items():
            if k in ("score_analysis", "learning_routine", "attendance"):
                continue
            raw_json[k] = v

    # Ensure identifiers are present on raw_json
    raw_json.setdefault("member_code", member_code)
    raw_json.setdefault("exam_test_code", exam_test_code)
    raw_json.setdefault("exam_div", exam_div)
    raw_json.setdefault("exam_name", exam_name)

    # Ensure member_code is present for feature synthesis (defensive).
    score_for_feature = dict(score_analysis) if isinstance(score_analysis, dict) else {}
    routine_for_feature = dict(learning_routine) if isinstance(learning_routine, dict) else {}
    attendance_for_feature = dict(attendance) if isinstance(attendance, dict) else {}
    score_for_feature.setdefault("member_code", member_code)
    routine_for_feature.setdefault("member_code", member_code)
    attendance_for_feature.setdefault("member_code", member_code)

    feature_json = build_feature_json_from_analytics(
        score=score_for_feature,
        routine=routine_for_feature,
        attendance=attendance_for_feature,
    )

    return {
        "member_code": member_code,
        "exam_test_code": exam_test_code,
        "learning_period_start": learning_period_start,
        "learning_period_end": learning_period_end,
        "exam_div": exam_div,
        "exam_name": exam_name,
        "course_code": course_code,
        # V2: explicitly inject these so the bootstrap agent can use them directly.
        "raw_json": raw_json,
        "feature_json": feature_json,
    }


@app.post("/batch-counsel", response_model=BatchCounselResponse)
async def batch_counsel(payload: BatchCounselPayloadV2) -> BatchCounselResponse:
    """
    Run the counseling pipeline for multiple students in a single request.

    Internally uses asyncio + semaphore to cap concurrency per container.
    Also logs batch start/end time and duration to help with monitoring.
    """
    batch_data: list[BatchCounselItemV2] = list(payload.batch_data or [])

    batch_size = len(batch_data)
    start_time = datetime.utcnow()
    logger.info(
        "Batch counsel started: size=%d, start_time=%s",
        batch_size,
        start_time.isoformat() + "Z",
    )

    sem = asyncio.Semaphore(settings.concurrency_limit)

    async def _run_one(item: BatchCounselItemV2) -> CounselResult:
        async with sem:
            state = _split_and_build_state_from_v2_item(item)
            item_start = datetime.utcnow()
            try:
                guide = await run_root_agent_once(state)
                return CounselResult(
                    member_code=str(state.get("member_code") or ""),
                    exam_test_code=str(state.get("exam_test_code") or ""),
                    course_code=state.get("course_code") if state.get("course_code") is not None else None,
                    status="success",
                    analysis_result=guide,
                    exam_div=str(state.get("exam_div") or ""),
                    exam_name=str(state.get("exam_name") or ""),
                )
            except Exception as e:
                logger.exception(
                    "Failed batch counseling for member_code=%s", state.get("member_code")
                )
                return CounselResult(
                    member_code=str(state.get("member_code") or ""),
                    exam_test_code=str(state.get("exam_test_code") or ""),
                    course_code=state.get("course_code") if state.get("course_code") is not None else None,
                    status="error",
                    analysis_result=None,
                    error=str(e),
                    exam_div=str(state.get("exam_div") or ""),
                    exam_name=str(state.get("exam_name") or ""),
                )

    all_results: list[CounselResult] = []

    # Process the incoming batch in logical chunks (e.g., 20 at a time) while
    # still honoring the global concurrency limit enforced by the semaphore.
    chunk_size = settings.batch_chunk_size
    logger.info(
        "Batch counsel processing in chunks: batch_size=%d, chunk_size=%d",
        batch_size,
        chunk_size,
    )

    for chunk in _chunked(batch_data, chunk_size):
        chunk_tasks = [_run_one(item) for item in chunk]
        chunk_results = await asyncio.gather(*chunk_tasks)
        all_results.extend(chunk_results)

    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    print(
        f"Batch counsel finished: size={batch_size}, "
        f"end_time={end_time.isoformat() + 'Z'}, duration_ms={duration_ms}"
    )

    # NOTE:
    #   generated_seq was previously assigned here based on batch order.
    #   As of now, we intentionally leave it as None for all items so that
    #   downstream systems treat both single and batch counsel the same.

    return BatchCounselResponse(
        total=len(all_results),
        results=list(all_results),
    )

