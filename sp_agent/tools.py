from __future__ import annotations
import os
import re
import json
import logging
import yaml
from typing import Any, Dict, List, Mapping, Tuple
from pydantic import BaseModel, Field
from google.adk.agents.readonly_context import ReadonlyContext


logger = logging.getLogger(__name__)

ALLOWED_ROOTS = (
    "sp_agent/knowledge",
    "sp_agent/raw_data",
)


def _is_allowed_path(path: str) -> bool:
    """Check if path is within allowed directories."""
    abs_path = os.path.abspath(path)
    for root in ALLOWED_ROOTS:
        if abs_path.startswith(os.path.abspath(root) + os.sep) or abs_path == os.path.abspath(root):
            return True
    return False


def _read_text(path: str, encoding: str = "utf-8") -> str:
    """Read text file with path validation."""
    if not _is_allowed_path(path):
        raise PermissionError(f"Path not allowed: {path}")
    with open(path, "r", encoding=encoding) as f:
        return f.read()


def load_text_file(path: str, encoding: str = "utf-8") -> str:
    """Load a text file and return its contents."""
    return _read_text(path, encoding)


def load_json_file(path: str, encoding: str = "utf-8") -> str:
    """Load a JSON file and return it as a formatted JSON string."""
    if not _is_allowed_path(path):
        raise PermissionError(f"Path not allowed: {path}")
    with open(path, "r", encoding=encoding) as f:
        data = json.load(f)
    return json.dumps(data, ensure_ascii=False, indent=2)


def extract_yaml_case_rules(yaml_text: str, code: str) -> str:
    """
    Extract the 'rules' block scalar string for a given case code from case_guides.yaml.
    
    Preferred approach:
      - Parse YAML via PyYAML (already in requirements) and return the matching
        case's 'rules' string.

    Fallback approach (defensive):
      - If YAML parsing fails for any reason, fall back to a lightweight text scan:
        find '- code: CODE' and capture the subsequent 'rules: |' block.
    
    Args:
        yaml_text: Content of the YAML file
        code: Case code to extract rules for
        
    Returns:
        Rules text for the specified case code
    """
    def _fallback_scan(yaml_text_inner: str, code_inner: str) -> str:
        lines = yaml_text_inner.splitlines()
        n = len(lines)

        # Find the block for the given code
        code_line_idx = -1
        code_pattern = re.compile(r"^\s*-\s+code:\s+" + re.escape(code_inner) + r"\s*$")
        for i, line in enumerate(lines):
            if code_pattern.match(line):
                code_line_idx = i
                break
        if code_line_idx == -1:
            raise ValueError(f"Case code not found in YAML: {code_inner}")

        # From code_line_idx, search for 'rules: |'
        rules_idx = -1
        rules_pattern = re.compile(r"^\s*rules:\s*\|\s*$")
        for i in range(code_line_idx + 1, n):
            if rules_pattern.match(lines[i]):
                rules_idx = i
                break
            # If we hit another '- code:' before rules, stop
            if re.match(r"^\s*-\s+code:\s+\S+", lines[i]):
                break
        if rules_idx == -1:
            raise ValueError(f"'rules: |' block not found for case {code_inner}")

        # Capture all indented lines following 'rules: |'
        captured: List[str] = []
        if rules_idx + 1 >= n:
            return ""

        next_line = lines[rules_idx + 1]
        indent_match = re.match(r"^(\s+)", next_line)
        content_indent = len(indent_match.group(1)) if indent_match else 0

        for i in range(rules_idx + 1, n):
            line = lines[i]
            # Stop if we hit a new top-level field or list item
            if re.match(r"^\s*-\s+code:\s+\S+", line):
                break
            # Capture only if indented at least content_indent (block scalar content)
            if len(line) >= content_indent and line[:content_indent].isspace():
                captured.append(line[content_indent:])
            else:
                # A less-indented line; likely end of block
                # But allow empty lines
                if line.strip() == "":
                    captured.append("")
                else:
                    break

        return "\n".join(captured).rstrip() + "\n"

    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            raise ValueError("YAML root is not a mapping")

        cases = data.get("cases")
        if not isinstance(cases, list):
            raise ValueError("YAML does not contain 'cases' list")

        for case in cases:
            if not isinstance(case, dict):
                continue
            case_code = case.get("code")
            if isinstance(case_code, str) and case_code.strip() == code:
                rules = case.get("rules", "")
                if rules is None:
                    rules = ""
                if not isinstance(rules, str):
                    rules = str(rules)
                return rules.rstrip() + "\n"

        raise ValueError(f"Case code not found in YAML: {code}")
    except Exception as e:
        logger.debug("YAML parse failed; falling back to text scan: %s", e)
        return _fallback_scan(yaml_text, code)


def substitute_variables(template: str, **variables: Any) -> str:
    """
    Simple variable substitution for {VAR} tokens in template.
    
    Args:
        template: Template string with {VAR} placeholders
        **variables: Variable name-value pairs to substitute
        
    Returns:
        Template with variables substituted
    """
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def load_case_guide_and_substitute(
    template: str,
    case_code: str,
    yaml_path: str = "sp_agent/knowledge/case_guides.yaml",
    encoding: str = "utf-8",
    **extra_variables: Any
) -> str:
    """
    Load case guide from YAML and substitute all variables into template.
    
    Args:
        template: Prompt template with {VAR} placeholders
        case_code: Case code to extract from YAML (will be available as {result})
        yaml_path: Path to case_guides.yaml file
        encoding: File encoding
        **extra_variables: Additional variables to substitute (e.g., summary)
        
    Returns:
        Rendered template with all variables substituted
    """
    # Load YAML and extract case guide
    yaml_text = _read_text(yaml_path, encoding=encoding)
    case_guideline = extract_yaml_case_rules(yaml_text, case_code)
    
    # Prepare all variables
    variables = {
        "result": case_code,
        "CASE_GUIDELINE": case_guideline,
        **extra_variables
    }
    
    # Substitute and return
    return substitute_variables(template, **variables)


# === Session-state helpers for per-student JSON data ===


def get_feature_and_raw_from_state(state: Mapping[str, Any]) -> Tuple[Any | None, Any | None]:
    """
    Fetch feature/raw JSON blobs from ADK session state.

    Expected keys:
      - feature_json: TT_feature_data_api_fin 형태 JSON (dict or JSON string)
      - raw_json: TT_종합분석_data 형태 JSON (dict or JSON string)
    """
    feature = state.get("feature_json")
    raw = state.get("raw_json")
    return feature, raw


def build_or_get_summary_from_state(readonly_ctx: ReadonlyContext) -> str:
    """
    Build or reuse a compact student summary based on session state.

    Priority:
      1) If state['summary'] exists and is non-empty string, reuse it.
      2) Else, read `feature_json` and `raw_json` from state, call convert_student_data,
         serialize to JSON string, store back into state['summary'] and return it.

    This keeps the data-flow for TT_feature_data_api_fin / TT_종합분석_data entirely
    session-based (no file I/O), while still reusing the existing pure-Python converter.
    """
    state = readonly_ctx.session.state

    existing_summary = state.get("summary")
    if isinstance(existing_summary, str) and existing_summary.strip():
        return existing_summary

    feature_json, raw_json = get_feature_and_raw_from_state(state)

    current_exam_name = state.get("exam_name")
    summary_dict: Dict[str, Any] = {}

    if feature_json is None or raw_json is None:
        logger.error(
            "Session state is missing feature_json or raw_json; "
            "unable to build compact student summary."
        )
    else:
        try:
            # convert_student_data can handle both JSON strings and dicts.
            summary_dict = convert_student_data(
                feature_json,
                raw_json,
                current_exam_name=current_exam_name,  # type: ignore[arg-type]
            )
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("Failed to compute student summary from session state: %s", e)
            summary_dict = {}

    summary_str = json.dumps(summary_dict, ensure_ascii=False, indent=2) if summary_dict else "{}"

    # Best-effort: cache into mutable invocation session state so later steps
    # (e.g. inject_session_state or other agents) can reuse {summary}.
    try:
        readonly_ctx._invocation_context.session.state["summary"] = summary_str  # type: ignore[attr-defined]
    except Exception:
        # Avoid breaking the flow if ADK internals change; summary_str is still returned.
        logger.debug("Could not cache summary into invocation state; continuing without cache.")

    return summary_str

"""
Data converter utilities for CANB counseling system.

This module implements pure-Python preprocessing that:
- takes two raw JSON inputs
  - TT_feature_data_api_fin.json  (long-term feature data)
  - TT_종합분석_data.json        (current exam + activity details)
- returns a compact summary JSON matching the schema described in
  data_summary_agent/prompt.py.

Core conversion logic is pure Python (no LLM). The high-level
`convert_student_data` function is suitable to be exposed as an
ADK Function Tool so that other agents can call it.
"""




class DataSummary(BaseModel):
    """Compact summary schema consumed by counseling generator."""

    exam_summary: Dict[str, Any] = Field(
        description="요약된 시험/레벨/퍼센트 추세 정보 블록"
    )
    subjects_current: str = Field(
        description="이번 회차 과목별 점수/퍼센트 한 줄 요약 (Grammar S(P%), Listening S(P%) ...)"
    )
    subjects_scores_trend: Dict[str, str] = Field(
        description="과목별 점수 추세 문자열 (Listening: a -> b -> c ...)"
    )
    readi_activity: Dict[str, Any] = Field(
        description="READi/온라인 수행률 관련 요약"
    )
    readi_scores: Dict[str, Any] = Field(
        description="READi/온라인 점수 관련 요약"
    )
    reading_overview: str = Field(
        description="최근 N개월 독서량 간단 요약 (예: '6: 4권, 7: 10권, ...')"
    )
    # NOTE:
    #   키 이름을 downstream에서 요구하는 형태에 맞추기 위해
    #   'attendance_overview' 대신 'Absence_overview'를 사용한다.
    absence_overview: str = Field(
        description="최근 N개월 결석 요약 (예: '8: 1회, 10: 1회, 11: 1회')"
    )
    exam_ranks: Dict[str, Any] = Field(
        default_factory=dict,
        description="각 시험별 등수 요약 (예: {'2025 여름학기 Hepta 1 MT1': '83/209'})",
    )
    learning_recommendation: Dict[str, Any] = Field(
        default_factory=dict,
        description="과목별 학습 추천 문구 요약 (예: {'Grammar': '약점 스킬 강화 학습, ...'})",
    )
    weak_skill: Dict[str, Any] = Field(
        default_factory=dict,
        description="과목별 약점 스킬 요약 (예: {'Reading': ['지표: ..., 스킬: ... (학생 0.0%, 평균 92.86%, 격차 92.86%)', ...]})",
    )


def _safe_get(d: Mapping[str, Any], path: List[str], default: Any = None) -> Any:
    """Safely traverse nested dict with a list of keys."""
    cur: Any = d
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _format_mt_trend(exams: List[Dict[str, Any]]) -> str:
    """
    Build total_MT_scores_trend string from MT-type exams.

    Example format:
      'MT1 238 -> MT2 260 -> MT1 260 -> MT2 247'

    Note:
      - MT trend 는 MT1, MT2 시험만 대상으로 한다.
        (예: Penta 레벨의 MT3 는 TT(종합평가)로 취급)
    """
    parts: List[str] = []
    for ex in exams:
        name = ex.get("exam_name", "")
        total = ex.get("total_score")

        # Only MT1 / MT2 are counted in MT trend.
        m = re.search(r"MT\s*([0-9]+)", name)
        if not m:
            continue
        mt_no = m.group(1)
        if mt_no not in ("1", "2"):
            # MT3 이상은 MT trend 에서 제외 (Penta MT3 는 TT trend 에서 처리)
            continue

        short = f"MT{mt_no}"
        label = f"{short} {total}" if total is not None else short
        parts.append(label)
    return " -> ".join(parts) if parts else "데이터 없음"


def _format_tt_trend(exams: List[Dict[str, Any]]) -> str:
    """
    Build total_TT_scores_trend string from TT-type exams.

    Example format:
      'Summer_TT 182.7 -> Fall_TT 222.2'

    Rules:
      - 기본적으로는 학기별 Term Test(또는 TT) 점수 추세를 보여준다.
      - Penta / Hexa 레벨에서는 실제 Term Test 대신 MT3 가 종합평가 역할을 하므로,
        해당 레벨의 경우 MT3 시험들만 골라서 학기 간 추세를 만든다.
    """
    if not exams:
        return "데이터 없음"

    # Penta / Hexa 레벨 여부를 exam_name 에서 판단
    def _is_penta_hexa(name: str) -> bool:
        return ("Penta" in name) or ("Hexa" in name)

    penta_hexa_exists = any(
        _is_penta_hexa(str(ex.get("exam_name", ""))) for ex in exams
    )

    filtered: List[Dict[str, Any]] = []
    if penta_hexa_exists:
        # Penta / Hexa 레벨이면 MT3 만 TT trend 대상으로 사용
        for ex in exams:
            name = str(ex.get("exam_name", ""))
            if "MT3" in name:
                filtered.append(ex)
    else:
        # 그 외 레벨은 Term Test / TT 이름을 가진 시험들만 사용
        for ex in exams:
            name = str(ex.get("exam_name", ""))
            if "Term Test" in name or "TT" in name:
                filtered.append(ex)

    # 필터링 결과가 비어 있으면 전체 exams 를 그대로 사용 (defensive fallback)
    if not filtered:
        filtered = exams

    # 날짜 기준 정렬 (과거 -> 최신)
    filtered = sorted(filtered, key=lambda e: str(e.get("exam_date", "")))

    parts: List[str] = []
    for ex in filtered:
        name = str(ex.get("exam_name", ""))
        total = ex.get("total_score")
        # Rough season detection from Korean name
        season = ""
        if "여름학기" in name:
            season = "Summer"
        elif "가을학기" in name:
            season = "Fall"

        # Penta / Hexa 의 MT3 인 경우 레이블에 MT3 를 명시
        if penta_hexa_exists and "MT3" in name:
            label_prefix = f"{season}_MT3".strip("_") if season else "MT3"
        else:
            label_prefix = f"{season}_TT".strip("_") if season else "TT"

        label = f"{label_prefix} {total}" if total is not None else label_prefix
        parts.append(label)

    return " -> ".join(parts) if parts else "데이터 없음"


def _format_subjects_current(raw_data: Dict[str, Any]) -> str:
    """
    Build 'subjects_current' like:
      'Phonics 60점, Reading 0점, ...'
    using only percentage as a 100점 만점 환산 점수.
    """
    scores = raw_data.get("exam_scores") or []
    parts: List[str] = []
    for item in scores:
        subj = item.get("subject_name")
        pct = item.get("score_percentage")
        if subj is None or pct is None:
            continue
        try:
            pct_val = float(pct)
            if pct_val.is_integer():
                pct_str = str(int(pct_val))
            else:
                pct_str = str(pct_val)
        except Exception:
            # 숫자로 파싱 안 되면 원문 그대로 사용
            pct_str = str(pct)

        parts.append(f"{subj} {pct_str}점")
    return ", ".join(parts) if parts else "데이터 없음"


def _format_subject_trend_for(
    feature_data: Dict[str, Any],
    subject_name: str,
    cutoff_exam_date: str | None = None,
    current_exam_name: str | None = None,
) -> str:
    """
    Build 'a -> b -> c -> d' style trend string for a subject from
    student_data.exams[*].subjects[*].score (점수 기준).

    Format example:
      'TT 40.0 -> MT1 80.4 -> MT2 87.1'

    """
    student = feature_data.get("student_data") or {}
    exams = student.get("exams") or []
    values: List[str] = []

    # If the current exam is MT1/MT2, do NOT include MT3 or TT/Term Test
    # in per-subject trends.
    current_is_mt12 = False
    if current_exam_name:
        m_cur = re.search(r"MT\s*([0-9]+)", str(current_exam_name))
        if m_cur and m_cur.group(1) in ("1", "2"):
            current_is_mt12 = True

    def _short_exam_label(exam: Mapping[str, Any]) -> str:
        """
        시험 이름에서 간단한 약어를 추출한다.
          - '... MT1' / '... MT2' / '... MT3'  -> 'MT1' / 'MT2' / 'MT3'
          - '... Term Test ...' 또는 '... TT ...' -> 'TT'
        그 외에는 빈 문자열을 반환한다.
        """
        name = str(exam.get("exam_name", ""))
        # MT1 / MT2 / MT3
        m = re.search(r"MT\s*([0-9]+)", name)
        if m:
            return f"MT{m.group(1)}"
        # TT / Term Test
        if "Term Test" in name or "TT" in name:
            return "TT"
        return ""

    for ex in exams:
        if cutoff_exam_date:
            ex_date = re.sub(r"[^0-9]", "", str(ex.get("exam_date", "")))
            if len(ex_date) >= 8 and ex_date[:8] > cutoff_exam_date:
                continue

        if current_is_mt12:
            name = str(ex.get("exam_name", ""))
            # exclude MT3 always when current is MT1/MT2
            m = re.search(r"MT\s*([0-9]+)", name)
            if m and m.group(1) == "3":
                continue
            # exclude all TT/Term Test exams when current is MT1/MT2
            if "Term Test" in name or "TT" in name:
                continue

        label = _short_exam_label(ex)
        for subj in ex.get("subjects") or []:
            if subj.get("subject_name") == subject_name:
                score = subj.get("score_percentage")
                if score is None:
                    score = subj.get("percentage")

                if score is not None:
                    if label:
                        values.append(f"{label} {score}")
                    else:
                        values.append(str(score))
    return " -> ".join(values) if values else "데이터 없음"


def _build_readi_activity(
    feature_data: Dict[str, Any], raw_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build readi_activity block combining:
    - overall assignment rate from feature_data
    - per-subject completion_rate from raw_data.activity_scores
    """
    student = feature_data.get("student_data") or {}
    readi = student.get("readi_alex") or {}
    features = readi.get("features") or {}
    overall_rate = features.get("ASGN_RATE")

    activity_scores = raw_data.get("activity_scores") or []
    per_subject: Dict[str, Any] = {}
    for item in activity_scores:
        subj = item.get("subject_type")
        rate = item.get("completion_rate")
        if subj and rate is not None:
            per_subject[subj] = f"{rate}%"

    result: Dict[str, Any] = {
        "activity_rate": f"{overall_rate}%" if overall_rate is not None else "데이터 없음",
    }
    result.update(per_subject)
    return result


def _build_readi_scores(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build readi_scores block from raw_data.activity_scores[*].average_score.
    """
    activity_scores = raw_data.get("activity_scores") or []
    result: Dict[str, Any] = {}
    for item in activity_scores:
        subj = item.get("subject_type")
        avg = item.get("average_score")
        if subj and avg is not None:
            result[subj] = avg
    return result


def _build_reading_overview(
    feature_data: Dict[str, Any],
    cutoff_year_month: str | None = None,
) -> str:
    """
    Build reading_overview string from readi_alex.monthly_records[*].alex_book_count.
    Example: '6: 4권, 7: 10권, 8: 15권'
    """
    student = feature_data.get("student_data") or {}
    readi = student.get("readi_alex") or {}
    records = readi.get("monthly_records") or []
    def _normalize_yyyymmdd(value: Any) -> str | None:
        if value is None:
            return None
        s = re.sub(r"[^0-9]", "", str(value))
        return s[:8] if len(s) >= 8 else None

    def _iter_year_months(start_yyyymm: str, end_yyyymm: str) -> List[str]:
        sy, sm = int(start_yyyymm[:4]), int(start_yyyymm[4:6])
        ey, em = int(end_yyyymm[:4]), int(end_yyyymm[4:6])
        out: List[str] = []
        y, m = sy, sm
        while (y < ey) or (y == ey and m <= em):
            out.append(f"{y:04d}{m:02d}")
            m += 1
            if m == 13:
                m = 1
                y += 1
        return out

    analysis = student.get("analysis_period") or {}
    start_date = _normalize_yyyymmdd(analysis.get("start"))
    end_date = _normalize_yyyymmdd(analysis.get("end"))
    timeline: List[str] = []
    if start_date and end_date:
        timeline = _iter_year_months(start_date[:6], end_date[:6])

    filtered: List[Tuple[str, int, int]] = []  # (yyyymm, month, count)
    for rec in records:
        month_raw = rec.get("month")
        count = rec.get("alex_book_count")
        if month_raw is None or count is None:
            continue
        try:
            m = int(str(month_raw).strip())
        except Exception:
            continue

        # Determine record yyyymm
        yyyymm: str | None = None
        if timeline:
            candidates = [ym for ym in timeline if int(ym[4:6]) == m]
            if len(candidates) == 1:
                yyyymm = candidates[0]
        # Fallback: no year info; just use month-only grouping
        if yyyymm is None:
            yyyymm = f"0000{m:02d}"

        if cutoff_year_month is not None and yyyymm != "0000" + f"{m:02d}":
            # Only apply cutoff if we have real YYYYMM
            if yyyymm > cutoff_year_month:
                continue

        try:
            c = int(count)
        except Exception:
            continue
        filtered.append((yyyymm, m, c))

    # Sort by yyyymm when available, otherwise by month
    filtered.sort(key=lambda x: (x[0], x[1]))
    parts = [f"{m}월: {c}권" for _, m, c in filtered]
    return ", ".join(parts) if parts else "데이터 없음"


def _build_attendance_overview(
    feature_data: Dict[str, Any],
    cutoff_year_month: str | None = None,
) -> str:
    """
    Build attendance_overview string from attendance.monthly_records[*].absence_count.
    Example: '8: 1회, 10: 1회, 11: 1회'
    """
    student = feature_data.get("student_data") or {}
    attendance = student.get("attendance") or {}
    records = attendance.get("monthly_records") or []
    def _normalize_yyyymmdd(value: Any) -> str | None:
        if value is None:
            return None
        s = re.sub(r"[^0-9]", "", str(value))
        return s[:8] if len(s) >= 8 else None

    def _iter_year_months(start_yyyymm: str, end_yyyymm: str) -> List[str]:
        sy, sm = int(start_yyyymm[:4]), int(start_yyyymm[4:6])
        ey, em = int(end_yyyymm[:4]), int(end_yyyymm[4:6])
        out: List[str] = []
        y, m = sy, sm
        while (y < ey) or (y == ey and m <= em):
            out.append(f"{y:04d}{m:02d}")
            m += 1
            if m == 13:
                m = 1
                y += 1
        return out

    analysis = student.get("analysis_period") or {}
    start_date = _normalize_yyyymmdd(analysis.get("start"))
    end_date = _normalize_yyyymmdd(analysis.get("end"))
    timeline: List[str] = []
    if start_date and end_date:
        timeline = _iter_year_months(start_date[:6], end_date[:6])

    filtered: List[Tuple[str, int, int]] = []  # (yyyymm, month, cnt)
    for rec in records:
        month_raw = rec.get("month")
        cnt = rec.get("absence_count")
        if month_raw is None or cnt is None:
            continue
        try:
            m = int(str(month_raw).strip())
        except Exception:
            continue

        yyyymm: str | None = None
        if timeline:
            candidates = [ym for ym in timeline if int(ym[4:6]) == m]
            if len(candidates) == 1:
                yyyymm = candidates[0]
        if yyyymm is None:
            yyyymm = f"0000{m:02d}"

        if cutoff_year_month is not None and yyyymm != "0000" + f"{m:02d}":
            if yyyymm > cutoff_year_month:
                continue

        try:
            c = int(cnt)
        except Exception:
            continue
        filtered.append((yyyymm, m, c))

    filtered.sort(key=lambda x: (x[0], x[1]))
    parts = [f"{m}월: {c}회" for _, m, c in filtered]
    return ", ".join(parts) if parts else "결석 없음"


def _build_exam_ranks(student_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build exam_ranks block from student_data.exams[*].rank / total_students.

    Example:
      {
        "2025 여름학기 Hepta 1 MT1": "83/209",
        ...
      }
    """
    exams = student_data.get("exams") or []
    result: Dict[str, Any] = {}
    for ex in exams:
        name = ex.get("exam_name")
        rank = ex.get("rank")
        total = ex.get("total_students")
        if not name or rank is None or total is None:
            continue
        result[str(name)] = f"{rank}/{total}"
    return result


def _is_current_exam_all_full_score(raw_data: Dict[str, Any]) -> bool:
    """
    Check whether the current exam's all subjects are full-score.

    Definition:
      - Look at raw_data.exam_scores[*].
      - Consider only rows where both subject_name and score_percentage are present.
      - If there is at least one such subject and every one has score_percentage == 100,
        return True.
      - Otherwise (no subjects, parse error, or any score_percentage != 100) return False.
    """
    exam_scores = raw_data.get("exam_scores") or []
    valid_items: List[Dict[str, Any]] = []

    for item in exam_scores:
        subj = item.get("subject_name")
        pct = item.get("score_percentage")
        if subj is None or pct is None:
            continue
        valid_items.append(item)

    if not valid_items:
        return False

    for item in valid_items:
        pct = item.get("score_percentage")
        try:
            pct_val = float(pct)
        except Exception:
            return False
        if pct_val != 100.0:
            return False

    return True


def _build_learning_recommendation(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build learning_recommendation block.

    Primary source:
      - raw_data.subject_learning_guidances[*].{subject_name, learning_recommendation}

    Special rules:
      - If the current exam's all subjects have score_percentage == 100
         return: {"General": "Alex 상위레벨 도서 읽기"}
        instead of using subject_learning_guidances.
      - Otherwise, use subject_learning_guidances, but DO NOT include subjects
        whose current exam score_percentage is 100 (they already achieved full score).
    """
    if _is_current_exam_all_full_score(raw_data):
        return {"General": "Alex 상위레벨 도서 읽기"}

    # Build a set of subjects with full score (score_percentage == 100)
    exam_scores = raw_data.get("exam_scores") or []
    full_score_subjects: set[str] = set()
    for item in exam_scores:
        subj = item.get("subject_name")
        pct = item.get("score_percentage")
        if subj is None or pct is None:
            continue
        try:
            pct_val = float(pct)
        except Exception:
            continue
        if pct_val == 100.0:
            full_score_subjects.add(str(subj))

    guidances = raw_data.get("subject_learning_guidances") or []
    result: Dict[str, Any] = {}
    for item in guidances:
        subj = item.get("subject_name")
        rec = item.get("learning_recommendation")
        if not subj or not rec:
            continue
        # Skip subjects that already have full score in the current exam.
        if str(subj) in full_score_subjects:
            continue
        # 공백 정리
        result[str(subj)] = str(rec).strip()
    return result


def _build_weak_skills(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build weak_skill block from raw_data.exam_scores[*].weak_skills.

    Output format (per subject):
    {
      "Reading": [
        "지표: 문맥에 맞게 단어 적용하기 / 스킬: Completing phrases or sentences with correct words to describe pictures (학생 0.0%, 평균 92.86%, 격차 92.86%)",
        ...
      ],
      "Phonics": [
        "지표: 자소-음소 인지 기반의 음소 결합 / 스킬: Blending onsets and long vowel rimes (학생 25.0%, 평균 94.64%, 격차 69.64%)"
      ]
    }
    """
    exam_scores = raw_data.get("exam_scores") or []
    result: Dict[str, Any] = {}

    for score in exam_scores:
        subject = score.get("subject_name")
        weak_list = score.get("weak_skills") or []
        if not subject or not weak_list:
            continue

        lines: List[str] = result.setdefault(str(subject), [])
        for ws in weak_list:
            indicator = ws.get("indicator_name")
            skill = ws.get("skill_name")
            student_pct = ws.get("student_percentage")
            avg_pct = ws.get("avg_percentage")
            gap = ws.get("gap")
            if not indicator and not skill:
                continue

            line = f"지표: {indicator or '-'} / 스킬: {skill or '-'}"
            # 숫자 정보가 있으면 괄호 안에 요약
            details: List[str] = []
            if student_pct is not None:
                details.append(f"학생 {student_pct}%")
            if avg_pct is not None:
                details.append(f"평균 {avg_pct}%")
            if gap is not None:
                details.append(f"격차 {gap}%")
            if details:
                line += f" ({', '.join(details)})"

            lines.append(line)

    return result


def build_compact_summary(
    feature_data: Dict[str, Any],
    raw_data: Dict[str, Any],
    current_exam_name: str | None = None,
) -> DataSummary:
    """
    Core converter: from feature + current exam JSON to compact DataSummary.

    Args:
        feature_data: Parsed dict from TT_feature_data_api_fin.json
        raw_data: Parsed dict from TT_종합분석_data.json
    """
    student = feature_data.get("student_data") or {}
    exams: List[Dict[str, Any]] = student.get("exams") or []

    def _normalize_yyyymmdd(value: Any) -> str | None:
        """
        Normalize a date-like value into 'YYYYMMDD' (digits only).

        Returns None if it cannot be normalized.
        """
        if value is None:
            return None
        s = re.sub(r"[^0-9]", "", str(value))
        if len(s) < 8:
            return None
        return s[:8]

    def _find_cutoff_exam_date(
        all_exams: List[Dict[str, Any]],
        requested_exam_name: str | None,
        inferred_exam_name: str | None,
    ) -> str | None:
        """
        Find cutoff exam_date (YYYYMMDD) for the current exam.

        Priority:
          1) Try to locate by requested_exam_name (exact match)
          2) Try fuzzy token match (season + MT/TT + year suffix) against requested_exam_name
          3) Fallback to inferred_exam_name (exact match)
          4) Latest available exam_date

        This is defensive because API request exam_name can be abbreviated
        (e.g. '25 가을학기 MT2') while feature_json may contain a longer name.
        """
        def _extract_tokens(name: str) -> dict:
            s = str(name)
            tokens: dict = {"season": None, "mt": None, "tt": False, "year2": None}
            if "여름학기" in s:
                tokens["season"] = "여름학기"
            elif "가을학기" in s:
                tokens["season"] = "가을학기"

            m = re.search(r"MT\s*([0-9]+)", s)
            if m:
                tokens["mt"] = m.group(1)

            if "Term Test" in s or re.search(r"\bTT\b", s) or "TT" in s:
                tokens["tt"] = True

            # year suffix: accept 2 or 4 digits, keep last 2 digits for loose matching
            y = re.search(r"([0-9]{2,4})", s)
            if y:
                tokens["year2"] = y.group(1)[-2:]
            return tokens

        def _try_exact(name: str) -> str | None:
            for ex in all_exams:
                if str(ex.get("exam_name", "")) == str(name):
                    return _normalize_yyyymmdd(ex.get("exam_date"))
            return None

        # 1) exact requested
        if requested_exam_name:
            d = _try_exact(requested_exam_name)
            if d:
                return d

        # 2) fuzzy requested tokens
        if requested_exam_name:
            req = _extract_tokens(requested_exam_name)
            scored: list[tuple[int, str, Dict[str, Any]]] = []
            for ex in all_exams:
                ex_name = str(ex.get("exam_name", ""))
                ex_tokens = _extract_tokens(ex_name)
                score = 0
                if req["mt"] and ex_tokens["mt"] == req["mt"]:
                    score += 3
                if req["season"] and ex_tokens["season"] == req["season"]:
                    score += 2
                if req["tt"] and ex_tokens["tt"]:
                    score += 3
                # loose year match: last 2 digits
                if req["year2"] and ex_tokens["year2"] == req["year2"]:
                    score += 1

                if score <= 0:
                    continue

                ex_date = _normalize_yyyymmdd(ex.get("exam_date")) or ""
                scored.append((score, ex_date, ex))

            if scored:
                # pick best score, then latest date among them
                scored.sort(key=lambda x: (x[0], x[1]))
                best = scored[-1][2]
                return _normalize_yyyymmdd(best.get("exam_date"))

        # 3) inferred exact
        if inferred_exam_name:
            d = _try_exact(inferred_exam_name)
            if d:
                return d

        # 4) latest exam_date
        dates = [_normalize_yyyymmdd(ex.get("exam_date")) for ex in all_exams]
        dates = [d for d in dates if d]
        return max(dates) if dates else None

    # Separate MT and TT exams.
    # 1) 우선 기존 Hepta/TT 코드(1007, 1010)를 그대로 지원하고,
    # 2) 그래도 비어 있으면 exam_name + level별 규칙으로 분류한다.
    #    - Penta / Hexa 레벨(예: 1054, 1055)에서는 MT3를 TT(종합평가)로 취급한다.
    mt_exams: List[Dict[str, Any]] = [
        e for e in exams if str(e.get("exam_type_code")) == "1007"
    ]
    tt_exams: List[Dict[str, Any]] = [
        e for e in exams if str(e.get("exam_type_code")) == "1010"
    ]

    if not mt_exams and not tt_exams:
        for ex in exams:
            name = str(ex.get("exam_name", ""))
            code = str(ex.get("exam_type_code", ""))

            # Penta / Hexa 레벨에서는 MT3 를 TT(종합평가)로 취급한다.
            is_penta_hexa_level = ("Penta" in name) or ("Hexa" in name)
            if (code in ("1054", "1055") or is_penta_hexa_level) and "MT3" in name:
                tt_exams.append(ex)
                continue

            if "Term Test" in name or "TT" in name:
                tt_exams.append(ex)
            elif "MT" in name:
                mt_exams.append(ex)

    # Current exam name:
    #   - 1순위: 외부에서 override 로 전달된 exam_name (예: CounselRequest.exam_name)
    #   - 2순위: feature_data 안에서 최신 TT 시험 이름, 없으면 최신 MT 시험 이름
    inferred_exam_name = None
    if tt_exams:
        inferred_exam_name = tt_exams[-1].get("exam_name")
    elif mt_exams:
        inferred_exam_name = mt_exams[-1].get("exam_name")

    effective_exam_name = current_exam_name or inferred_exam_name

    # Cutoff date: trim trends/overviews to the current exam (inclusive).
    # Use requested current_exam_name for cutoff lookup (even if abbreviated),
    # fall back to inferred exam name or latest date.
    cutoff_exam_date = _find_cutoff_exam_date(
        exams,
        requested_exam_name=current_exam_name,
        inferred_exam_name=inferred_exam_name,
    )

    cutoff_year_month: str | None = cutoff_exam_date[:6] if cutoff_exam_date else None

    # Level group variation:
    # - Compare level between 학기별 MT1 시험 (e.g. 여름학기 MT1 vs 가을학기 MT1).
    # - Example exam_name: "2025 여름학기 Hepta 1 MT1"
    def _extract_level(name: str) -> str | None:
        # Look for patterns like "Hepta 1", "Octa 2" and normalize to "Hepta1"
        m = re.search(r"(Penta|Hexa|Hepta|Octa|Nona)\s*([0-9]+)", name)
        if not m:
            return None
        return f"{m.group(1)}{m.group(2)}"

    def _detect_season(name: str) -> str | None:
        if "여름학기" in name:
            return "Summer"
        if "가을학기" in name:
            return "Fall"
        return None

    level_group_variation = "데이터 없음"
    # 1단계: 학기별 MT1만 모아서, 가장 이른 학기 MT1과 가장 늦은 학기 MT1의 레벨 비교
    season_mt1: Dict[str, Dict[str, Any]] = {}
    for ex in mt_exams:
        name = ex.get("exam_name", "")
        if "MT1" not in name:
            continue
        season = _detect_season(name)
        if not season:
            continue
        prev = season_mt1.get(season)
        if not prev or str(ex.get("exam_date", "")) < str(prev.get("exam_date", "")):
            season_mt1[season] = ex

    if season_mt1:
        # season_mt1에는 각 학기의 MT1 중 가장 빠른 시험이 들어 있음
        sorted_by_date = sorted(
            season_mt1.values(),
            key=lambda e: str(e.get("exam_date", "")),
        )
        start_exam = sorted_by_date[0]
        end_exam = sorted_by_date[-1]
        start_level = _extract_level(start_exam.get("exam_name", ""))
        end_level = _extract_level(end_exam.get("exam_name", ""))
        if start_level or end_level:
            level_group_variation = f"{start_level or '알 수 없음'} -> {end_level or '알 수 없음'}"
    else:
        # 2단계 fallback:
        #   MT1이 전혀 없는 레벨(예: Penta 2 MT2/MT3)에서도
        #   exam_name 안에 레벨 정보가 있으면 무조건 variation을 만들어 준다.
        level_exams: List[Dict[str, Any]] = []
        for ex in exams:
            name = ex.get("exam_name", "")
            if _extract_level(name):
                level_exams.append(ex)

        if level_exams:
            sorted_by_date = sorted(
                level_exams,
                key=lambda e: str(e.get("exam_date", "")),
            )
            start_exam = sorted_by_date[0]
            end_exam = sorted_by_date[-1]
            start_level = _extract_level(start_exam.get("exam_name", "")) or "알 수 없음"
            end_level = _extract_level(end_exam.get("exam_name", "")) or "알 수 없음"
            level_group_variation = f"{start_level} -> {end_level}"

    # Score features
    score_features = student.get("score_features") or {}
    pct = score_features.get("PCT")
    pct_tr = score_features.get("PCT_TR") or []
    
    # Note: 원래 코드에서는 현재 시험이름을 추출하는 로직이 있었으나, 임시 하드코딩
    exam_summary = {
        "current_exam_name": effective_exam_name or "데이터 없음",
        "total_MT_scores_trend": _format_mt_trend(mt_exams),
        "total_TT_scores_trend": _format_tt_trend(tt_exams),
        "level_group_variation": level_group_variation,
        "PCT": str(pct) if pct is not None else "데이터 없음",
        "PCT_TR": " -> ".join(str(v) for v in pct_tr) if pct_tr else "데이터 없음",
        "PCT_TT_TR": "데이터 없음",  # 필요시 TT 전용 피처에서 확장 가능
    }

    subjects_current = _format_subjects_current(raw_data)
    subjects_scores_trend = {
        "Phonics": _format_subject_trend_for(
            feature_data,
            "Phonics",
            cutoff_exam_date=cutoff_exam_date,
            current_exam_name=effective_exam_name,
        ),
        "Listening": _format_subject_trend_for(
            feature_data,
            "Listening",
            cutoff_exam_date=cutoff_exam_date,
            current_exam_name=effective_exam_name,
        ),
        "Reading": _format_subject_trend_for(
            feature_data,
            "Reading",
            cutoff_exam_date=cutoff_exam_date,
            current_exam_name=effective_exam_name,
        ),
        "Vocabulary": _format_subject_trend_for(
            feature_data,
            "Vocabulary",
            cutoff_exam_date=cutoff_exam_date,
            current_exam_name=effective_exam_name,
        ),
        "Grammar": _format_subject_trend_for(
            feature_data,
            "Grammar",
            cutoff_exam_date=cutoff_exam_date,
            current_exam_name=effective_exam_name,
        ),
    }

    readi_activity = _build_readi_activity(feature_data, raw_data)
    readi_scores = _build_readi_scores(raw_data)
    reading_overview = _build_reading_overview(
        feature_data, cutoff_year_month=cutoff_year_month
    )
    absence_overview = _build_attendance_overview(
        feature_data, cutoff_year_month=cutoff_year_month
    )
    exam_ranks = _build_exam_ranks(student)
    learning_recommendation = _build_learning_recommendation(raw_data)
    weak_skill = _build_weak_skills(raw_data)

    return DataSummary(
        exam_summary=exam_summary,
        subjects_current=subjects_current,
        subjects_scores_trend=subjects_scores_trend,
        readi_activity=readi_activity,
        readi_scores=readi_scores,
        reading_overview=reading_overview,
        absence_overview=absence_overview,
        exam_ranks=exam_ranks,
        learning_recommendation=learning_recommendation,
        weak_skill=weak_skill,
    )


def convert_student_data(
    feature_json: Any,
    raw_json: Any,
    current_exam_name: str | None = None,
) -> Dict[str, Any]:
    """
    High-level converter intended to be used as an ADK Function Tool.

    Args:
        feature_json: JSON 문자열 또는 dict (TT_feature_data_api_fin.json)
        raw_json: JSON 문자열 또는 dict (TT_종합분석_data.json)

    Returns:
        DataSummary 스키마에 맞춘 compact summary JSON(dict)
    """
    if isinstance(feature_json, str):
        feature_data = json.loads(feature_json)
    else:
        feature_data = feature_json

    if isinstance(raw_json, str):
        raw_data = json.loads(raw_json)
    else:
        raw_data = raw_json

    # StudentDataBootstrap 이 생성한 feature_json 은 score_features / readi_alex /
    # attendance 등을 top-level 에 둘 수 있으므로, summary 변환 전에
    # canonical 샘플(TT_feature_data_api_fin.json)과 맞게 student_data 내부로
    # 한 번 정규화해둔다.
    if isinstance(feature_data, dict):
        student = feature_data.get("student_data")
        if not isinstance(student, dict):
            student = {}
            feature_data["student_data"] = student
        for key in ("score_features", "exam_detail_features", "readi_alex", "attendance"):
            if key in feature_data and key not in student:
                student[key] = feature_data[key]

    summary = build_compact_summary(feature_data, raw_data, current_exam_name=current_exam_name)

    # SUMMARY_DEBUG=1 인 경우, 생성된 summary 를 로그로 남긴다.
    if os.getenv("SUMMARY_DEBUG", "0") == "1":
        try:
            logger.info(
                "📄 Student summary (convert_student_data):\n%s",
                json.dumps(summary.model_dump(exclude_none=True), ensure_ascii=False, indent=2),
            )
        except Exception:
            # 로깅 실패는 무시
            pass

    # Pydantic 모델을 dict로 반환하여 그대로 JSON 직렬화 가능하게 함
    return summary.model_dump(exclude_none=True)


if __name__ == "__main__":  # pragma: no cover - manual summary preview helper
    """
    간단 수동 테스트:
      python -m sp_agent.tools
    를 실행하면 sp_agent/raw_data 샘플 JSON 2개를 읽어서
    summary 변환 결과를 stdout 에 출력한다.
    """
    from pathlib import Path

    base = Path(__file__).resolve().parent / "raw_data"
    feature_path = base / "TT_feature_data_api_fin.json"
    raw_path = base / "TT_종합분석_data.json"

    feature_text = feature_path.read_text(encoding="utf-8")
    raw_text = raw_path.read_text(encoding="utf-8")

    summary_dict = convert_student_data(feature_text, raw_text)
    print(json.dumps(summary_dict, ensure_ascii=False, indent=2))


def convert_student_data_tool(
    feature_json: str,
    raw_json: str,
) -> Dict[str, Any]:
    """
    ADK Function Tool wrapper for student data conversion.

    This wrapper has a simple, tool-friendly signature:

      - feature_json: JSON 문자열 (TT_feature_data_api_fin.json 형태)
      - raw_json: JSON 문자열 (TT_종합분석_data.json 형태)

    It delegates to `convert_student_data` and returns the compact
    summary JSON as a dict, ready to be used by other agents.
    """
    return convert_student_data(feature_json, raw_json)
