from __future__ import annotations

import json
import logging
from typing import Any, Dict, Mapping

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from sp_agent.mapping import (
    build_feature_json_from_analytics,
    build_raw_json_from_exam_performance,
)
from sp_agent.tools import convert_student_data
from sp_agent.utils.performance_logger import get_tracker

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> Dict[str, Any]:
    """Best-effort: coerce JSON-ish value into a dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


class StudentDataBootstrapAgentV2(BaseAgent):
    """
    V2 bootstrap agent for CANB counseling system.

    Priority order:
      1) If session.state already contains BOTH `feature_json` and `raw_json`,
         reuse them and only compute+cache `summary`.
      2) Else if session.state contains `student_payload` (legacy single-student path),
         derive `feature_json`/`raw_json` from it.
      3) Else raise an error (offline policy: no external API calls).

    Outputs (always):
      - feature_json: dict
      - raw_json: dict
      - summary: JSON string (so downstream prompt injectors can reuse it)
    """

    async def _run_async_impl(self, ctx):
        tracker = get_tracker()
        tracker.start("student_data_bootstrap_v2")

        state = ctx.session.state
        member_code = state.get("member_code")
        exam_test_code = state.get("exam_test_code")
        learning_period_start = state.get("learning_period_start")
        learning_period_end = state.get("learning_period_end")
        exam_name = state.get("exam_name")

        # --- (1) State-first mode: raw_json/feature_json already injected ------
        existing_feature = state.get("feature_json")
        existing_raw = state.get("raw_json")
        if existing_feature is not None and existing_raw is not None:
            logger.info(
                "StudentDataBootstrapAgentV2 using injected feature_json/raw_json "
                "(member_code=%s, exam_test_code=%s)",
                member_code,
                exam_test_code,
            )
            feature_json = _as_dict(existing_feature)
            raw_json = _as_dict(existing_raw)

            summary_dict: Dict[str, Any] = convert_student_data(
                feature_json,
                raw_json,
                current_exam_name=str(exam_name) if exam_name is not None else None,
            )
            summary_str = json.dumps(summary_dict, ensure_ascii=False, indent=2)

            actions = EventActions()
            actions.state_delta["feature_json"] = feature_json
            actions.state_delta["raw_json"] = raw_json
            actions.state_delta["summary"] = summary_str

            content = types.Content(
                parts=[types.Part.from_text(text="Student data bootstrapped (state-first).")]
            )
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=content,
                actions=actions,
            )

            duration = tracker.end("student_data_bootstrap_v2")
            logger.info(
                "🧱 Student Data Bootstrap V2(state-first): Completed in %.2fs "
                "(member_code=%s, exam_test_code=%s)",
                duration,
                member_code,
                exam_test_code,
            )
            return

        # --- (2) Legacy payload mode (single-student /counsel path) ------------
        student_payload = state.get("student_payload")
        if isinstance(student_payload, dict):
            logger.info(
                "StudentDataBootstrapAgentV2 using student_payload from session state "
                "(member_code=%s, exam_test_code=%s)",
                member_code,
                exam_test_code,
            )

            score = student_payload.get("score_analysis") or {}
            routine = student_payload.get("learning_routine") or {}
            attendance = student_payload.get("attendance") or {}

            # performance: all keys except analytics blocks
            performance: Dict[str, Any] = {}
            for key, value in student_payload.items():
                if key in ("score_analysis", "learning_routine", "attendance"):
                    continue
                performance[key] = value

            # Backfill learning_period_start/end into performance if missing.
            analysis_period = {}
            if isinstance(score, dict):
                analysis_period = score.get("analysis_period") or {}
            if (
                "learning_period_start" not in performance
                and isinstance(analysis_period, dict)
                and analysis_period.get("start")
            ):
                performance["learning_period_start"] = analysis_period.get("start")
            if (
                "learning_period_end" not in performance
                and isinstance(analysis_period, dict)
                and analysis_period.get("end")
            ):
                performance["learning_period_end"] = analysis_period.get("end")

            feature_json = build_feature_json_from_analytics(
                score=score if isinstance(score, Mapping) else {},
                routine=routine if isinstance(routine, Mapping) else {},
                attendance=attendance if isinstance(attendance, Mapping) else {},
            )
            raw_json = build_raw_json_from_exam_performance(performance=performance)

        # --- (3) Offline policy: no API-fetch mode -----------------------------
        else:
            tracker.end("student_data_bootstrap_v2")
            raise ValueError(
                "Offline policy: raw_json/feature_json (or student_payload) must be provided "
                "in session.state; external CANB API fetch is disabled."
            )

        # Common: compute summary and emit state delta
        summary_dict = convert_student_data(
            feature_json,
            raw_json,
            current_exam_name=str(exam_name) if exam_name is not None else None,
        )
        summary_str = json.dumps(summary_dict, ensure_ascii=False, indent=2)

        actions = EventActions()
        actions.state_delta["feature_json"] = feature_json
        actions.state_delta["raw_json"] = raw_json
        actions.state_delta["summary"] = summary_str

        content = types.Content(
            parts=[types.Part.from_text(text="Student data bootstrapped (v2).")]
        )
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=content,
            actions=actions,
        )

        duration = tracker.end("student_data_bootstrap_v2")
        logger.info(
            "🧱 Student Data Bootstrap V2: Completed in %.2fs (member_code=%s, exam_test_code=%s)",
            duration,
            member_code,
            exam_test_code,
        )
