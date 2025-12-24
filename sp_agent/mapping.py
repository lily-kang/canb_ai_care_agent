"""
JSON mapping utilities for sp_agent (offline).

This project no longer calls the CANB external API from this codebase.
This module keeps only the deterministic mapping helpers that shape
incoming payloads into the internal structures consumed by the summary
pipeline:

  - feature_json (TT_feature_data_api_fin-style)
  - raw_json     (TT_종합분석_data-style)

If you need network fetchers again in the future, implement them in a
separate module so this file stays pure and testable.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping


def build_feature_json_from_analytics(
    score: Mapping[str, Any],
    routine: Mapping[str, Any],
    attendance: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Build internal feature_json from analytics endpoints.

    Target shape is aligned with sample TT_feature_data_api_fin.json:
        {
          "student_data": { ... },
          "score_features": { ... },
          "exam_detail_features": { ... },
          "readi_alex": { ... },
          "attendance": { ... }
        }

    Because the exact API schemas may evolve, this function is intentionally
    defensive:
      - It uses .get(..., {}) everywhere.
      - It tries a few common key patterns before giving up.

    Adjust this mapping once the analytics response formats are finalized.
    """

    # student_data may already be present as a nested object in one of the
    # analytics responses. Prefer explicit blocks if available.
    student_data: Dict[str, Any] = {}
    for src in (score, routine, attendance):
        existing = src.get("student_data")
        if isinstance(existing, Mapping):
            student_data = dict(existing)
            break

    # Fallback: synthesize minimal student_data from top-level hints.
    if not student_data:
        synthesized: Dict[str, Any] = {}
        for key in ("member_code", "analysis_period", "exams"):
            if key in score:
                synthesized[key] = score[key]
            elif key in routine:
                synthesized[key] = routine[key]
            elif key in attendance:
                synthesized[key] = attendance[key]
        student_data = synthesized

    # score_features: where PCT / PCT_TR / SCORE_CHG / ... live.
    score_features = {}
    # Prefer explicit "score_features" block if backend provides it.
    if isinstance(score.get("score_features"), Mapping):
        score_features = dict(score["score_features"])  # type: ignore[index]
    # Otherwise, try a generic "features" key.
    elif isinstance(score.get("features"), Mapping):
        score_features = dict(score["features"])  # type: ignore[index]

    # exam_detail_features: subject diff, etc.
    exam_detail_features = {}
    if isinstance(score.get("exam_detail_features"), Mapping):
        exam_detail_features = dict(score["exam_detail_features"])  # type: ignore[index]

    # readi_alex: learning-routine API 를 그대로 감싸는 단순 매핑.
    # 현재 learning-routine 응답 형태:
    # {
    #   "member_code": "...",
    #   "analysis_period": {...},
    #   "monthly_records": [...],
    #   "features": {...}
    # }
    # 여기서 monthly_records / features 만 뽑아서 readi_alex 블록으로 사용한다.
    readi_alex: Dict[str, Any] = {
        "monthly_records": routine.get("monthly_records") or [],
        "features": routine.get("features") or {},
    }

    # attendance: attendance API 에서 monthly_records / features 만 단순 매핑.
    attendance_block: Dict[str, Any] = {
        "monthly_records": attendance.get("monthly_records") or [],
        "features": attendance.get("features") or {},
    }

    feature_json: Dict[str, Any] = {
        "student_data": student_data,
        "score_features": score_features,
        "exam_detail_features": exam_detail_features,
        "readi_alex": readi_alex,
        "attendance": attendance_block,
    }
    return feature_json


def build_raw_json_from_exam_performance(
    performance: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Build internal raw_json (TT_종합분석_data-style) from exam performance.

    The sample TT_종합분석_data.json under sp_agent/raw_data/ appears to be
    very close to the performance endpoint payload, so by default we simply
    return a shallow copy of the performance dict.

    If the backend response diverges, adjust this mapping accordingly to
    ensure at least these fields exist at top level:
      - exam_test_code
      - exam_scores (list with subject_name, correct_score, score_percentage)
      - activity_scores (for READi-related features)
    """
    # Make a shallow copy so callers can mutate without affecting the original.
    return dict(performance)


def debug_dump_json(obj: Any) -> str:
    """
    Helper for logging pretty-printed JSON structures during development.

    Not used in the main pipeline, but handy for temporary debugging.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except TypeError:
        return repr(obj)

