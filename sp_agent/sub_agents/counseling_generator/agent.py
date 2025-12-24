import json
import os
from datetime import datetime
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils.instructions_utils import inject_session_state
from .prompt import COUNSELING_GENERATOR_PROMPT
from typing import List
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from sp_agent.utils.performance_logger import get_tracker, log_performance_summary
from sp_agent.tools import (
    load_text_file,
    extract_yaml_case_rules,
    build_or_get_summary_from_state,
)
import logging
from .schema import first_schema, second_schema, third_schema, fourth_schema

logger = logging.getLogger(__name__)

## 모델 설정
# Provider/model
MODEL_GPT_5 = "openai/gpt-4.1" 
MODEL_GEMINI = "gemini-2.5-flash"


async def build_counseling_base_context(readonly_ctx: ReadonlyContext) -> dict:
    """
    Build and cache the shared counseling context used by all sections.

    Returns a dict with:
      - case_code: selected case code string
      - case_guideline: YAML rules text for the case
      - summary_str: JSON string summary of student data
    """
    state = readonly_ctx.session.state

    # 1) Parse case_code from `result` in session state.
    # case_selector_agent is expected to output a plain string case code.
    raw_result = state.get("result")
    case_code = raw_result.strip().strip('"') if isinstance(raw_result, str) else ""
    if not case_code:
        # Fallback: leave a sentinel so it's obvious in the prompt
        case_code = "UNKNOWN_CASE_CODE"

    # 2) Compute compact student summary and store into session state.
    #    This now uses per-session JSON from session state (feature_json/raw_json),
    #    not static files, and reuses any existing cached summary if available.
    try:
        summary_str = build_or_get_summary_from_state(readonly_ctx)
    except Exception as e:
        logger.error("Failed to compute student summary from session state: %s", e)
        summary_str = "{}"

    # 3) Knowledge file을 로드하고 case_code에 해당하는 규칙만 추출
    yaml_text = load_text_file("sp_agent/knowledge/case_guides.yaml")
    try:
        case_guideline = extract_yaml_case_rules(yaml_text, case_code)
    except Exception:
        # If extraction fails, keep a clear placeholder
        case_guideline = f"[No rules found for case_code={case_code}]"

    return {
        "case_code": case_code,
        "case_guideline": case_guideline,
        "summary_str": summary_str,
    }


# === Section-specific instruction builders ===

async def build_instruction_avoided_and_overall(readonly_ctx: ReadonlyContext) -> str:
    """
    Build instruction for the combined '지양 표현' + '총평' section.
    """
    context = await build_counseling_base_context(readonly_ctx)
    case_code = context["case_code"]
    case_guideline = context["case_guideline"]
    summary_str = context["summary_str"]

    return f"""
You generate ONLY the '지양 표현' and '총평' sections of a CANB counseling guide in Korean.

Follow these rules:
- Use [Student Data] as the primary source.
- Use [Case Guides] only for tone, focus, and strategy hints.
- Do NOT copy example sentences from [Case Guides].
- Do NOT mention case_code or case_name explicitly.

Section (0) 지양 표현:
- Provide exactly 2 example sentences, but do NOT wrap them in quotation marks.  
e.g. 이 과목 때문에 점수가 떨어졌어요., 여기가 펑크났네요.
- 1 to 2 sentences explaining what to avoid.

Section (1) 총평:
- Bullet format. 5 to 6 sentences. 
- All bullet sentences MUST start with "-" (a hyphen, No other bullet symbols "•")
- Use noun-ending style (“~흐름임”, “~상태임”).  
- Include: performance trend vs previous test, subject balance, READi, Alex, attendance, interpretation of current performance.  
- If any metric such as READi, Alex, or reading count is “0” or empty, interpret it as “The student is considered to have done little or no activity”, Never use the expressions “missing data,” “no data,” or “insufficient information.”
- IMPORTANT: In '총평', wrap the most important phrases with double asterisks to emphasize critical points.
- If the current exam is MT3 or Term Test, DO NOT compare its score with previous MT tests
- Interpret score changes under 15 points as normal variation, and score changes of 15 points or more as meaningful; never call a ≥15 change “소폭/경미한”.
- Terminology Rule : 1) Do not use '소폭'. 2) READi 수행률 3) If the data is empty or zero in Alex & READi, do NOT describe it as “no data” or “missing information.”. Interpret it as “최근 활동이 이루어지지 않았음.”

Output requirements:
- Output MUST be valid JSON.
- No markdown code fences, no comments.
- Return this exact JSON shape:
{{
  "sections": {{
    "avoid": {{
      "id": "avoid",
      "title": "지양 표현",
      "avoid_example": ["...", "..."],
      "avoid_summary": "..."
    }},
    "summary": {{
      "id": "summary",
      "title": "총평",
      "content": "..."
    }}
  }}
}}

Below is the information required for generating the counseling script.

[Case Code]
{case_code}

[Case Guides]
{case_guideline}

[Student Data]
{summary_str}
"""


async def build_instruction_data_guide(readonly_ctx: ReadonlyContext) -> str:
    """
    Build instruction for the '데이터 해석 가이드' section.
    """
    context = await build_counseling_base_context(readonly_ctx)
    case_code = context["case_code"]
    case_guideline = context["case_guideline"]
    summary_str = context["summary_str"]

    return f"""
You generate ONLY the '데이터 해석 가이드' section in Korean.

Use [Student Data] as the numeric source and [Case Guides] as tone/style guidance.
Do NOT copy example sentences and do NOT mention case_code/case_name.

### LEVEL-BASED SUBJECT RULE
Use the student's level from [Student Data] to decide **which subjects to output**.
- Penta Level:
  subjects = [ "Phonics", "Reading" ]
  + always include: [ "READi", "Alex" ]

- Hexa Level:
  subjects = [ "Listening", "Reading", "Vocabulary" ]
  + always include: [ "READi", "Alex" ]
  (NO Grammar)

- Other Levels (Hepta, Octa, Nona, Deca 등 일반레벨):
  subjects = [ "Listening", "Reading", "Vocabulary", "Grammar" ]
  + always include: [ "READi", "Alex" ]

* Only output the subjects allowed for that level.

### MT vs Term Test Rules:
- Identify current exam type from [Student Data].
- If current exam is **MT**:
  • Compare only with previous MT values using scores, percentages, subject balance.
  • If score change is **±15**, do NOT call it "소폭", "경미한".
- If current exam is **Term Test or MT3 (Penta)**:
  • DO NOT compare Term Test **scores** with any MT scores.
  • Use ONLY rank, and TT-level cohort position to explain in **natural-language interpretation**.
  • No raw “214/586” or “퍼센타일 36.52” outputs.
  • If a level-group change exists, interpret adaptation rather than score gain/loss.

### Numeric Grounding Rules (MANDATORY):
- Each section (Listening, Reading, Vocabulary, Grammar, READi, Alex) MUST explicitly cite:
  • at least one numeric value (score, trend, count, rank)

### Constraints:
- Avoid 서열 표현 such as “상위권 아님”, “중간 수준”, “높지 않음”.
- No mention of the length of the passage in the 'Reading' section
- Terminology Rule : achievement rate -> '성취율', When referring to READi: activity rate-> '수행률', Alex -> '독서량'
- For Alex: If the data is empty or zero, do NOT describe it as “no data” or “missing information.”  
  Interpret it as “독서량이 없었음” or “최근 독서 활동이 이루어지지 않았음.”

### Section Output Rules:
- Create a guide to determine what patterns exist, what the likely causes are, and what points to emphasize.
- bullet-style, one or two explanations each for Listening, Reading, Vocabulary, Grammar, READi, Alex.
- Sentences should end with noun endings (“~임”, “~함”).
- Finish with “상담 Point”, “상담 Point” MUST be written as ONE single sentence.
    - Write a data-grounded conclusion sentence that includes:
  • key numeric evidence (e.g., 점수, 수행률, 독서량)
  • current learning status interpretation
  • what the instructor should guide or emphasize NEXT for this student.
- Output MUST be valid JSON using the structure below.

{{
  "sections": {{
    "guide": {{
      "id": "guide",
      "title": "데이터 해석 가이드",
      "subjects": [
        {{
          "label": "Phonics",
          "content": ".."
        }},
        ...
      ],
      "counsel_point": {{
        "label": "상담 Point",
        "content": ".."
      }}
    }}
  }}
}}

Below is the information required for generating.

[Case Code]
{case_code}

[Case Guides]
{case_guideline}

[Student Data]
{summary_str}
"""


async def build_instruction_behavior(readonly_ctx: ReadonlyContext) -> str:
    """
    Build instruction for the '행동' section.
    """
    context = await build_counseling_base_context(readonly_ctx)
    case_code = context["case_code"]
    case_guideline = context["case_guideline"]
    summary_str = context["summary_str"]

    return f"""
You generate ONLY the '행동' section of a CANB parent counseling guide in Korean.

Follow these rules:
- Use [Student Data] as the primary source for linking behavior and performance.
- Use [Case Guides] for tone, focus, and strategy hints.
- Do NOT copy example sentences from [Case Guides].
- Do NOT mention case_code or case_name explicitly.
- '긴 글', '긴 지문' 등의 표현을 사용하지 마세요.

Section (3) 행동 consists of two parts:

(수업 관찰)
- 1 to 3 bullet-style sentences.
- Each bullet describes concrete classroom behaviors the instructor should actively observe and note during lessons.
- Suggest to check whether specific behaviors changed and how that links to scores.
- Terminology Rule : '도전 난이도' -> '어려운 문제'

(학부모 확인 요청)
- 1 to 2 bullet-style sentences.
- Suggest what parents can observe or ask at home, connected to the current performance.

Output requirements:
- Output MUST be valid JSON.
- No markdown code fences, no comments.
- Use this exact structure and Korean keys:
{{
  "sections": {{
    "behavior": {{
      "id": "behavior",
      "title": "행동",
      "acts": [
        {{
          "label": "수업 관찰",
          "items": ["...", "..."]
        }},
        {{
          "label": "학부모 확인 요청",
          "items": ["...", "..."]
        }}
      ]
    }}
  }}
}}

Below is the information required for generating the counseling script.

[Case Code]
{case_code}

[Case Guides]
{case_guideline}

[Student Data]
{summary_str}
"""


async def build_instruction_closing(readonly_ctx: ReadonlyContext) -> str:
    """
    Build instruction for the '마무리' section.
    """
    context = await build_counseling_base_context(readonly_ctx)
    case_code = context["case_code"]
    case_guideline = context["case_guideline"]
    summary_str = context["summary_str"]

    return f"""
You generate ONLY the '마무리' section in Korean.

Use [Student Data] — especially the "learning_recommendation" field — to create data-aligned and personalized recommendations.  
Use [Case Guides] for tone and strategic direction.  
Do NOT copy example sentences from Case Guides.  
Do NOT mention case_code or case_name.

Section Rules:
(추천 활동)
- bullet-style. Maximum 3 bullets.
- Primarily use the information in "learning recommendation" of [Student Data] (e.g., 스킬 강화, 독서 목표 등).
- Each bullet MUST follow this format:
  "Activity or Strategy Label: concise one-line purpose or effect"
- Do NOT write full sentences.

### Fallback Rule
- If "learning recommendation" is empty, missing, or does not contain explicit activity/strategy names:
  • Refer to the "weak_skill" keys in [Student Data].
  • Generate strategy-based activity labels that focus on strengthening those weak skills.
  • Use noun-ending style labels and descriptions .
  • Do NOT invent program names.
  
(온라인·도서 강화 방향)
- Provide like bullets.
- READi, Alex's action strategy based on data from [Student Data].

(마무리 멘트)
- Provide exactly one short, supportive sentence. 
- Mention which stage student is in: "준비/도약/회복/기초 형성", and emphasize the child's strengths and potential, briefly outline the division of roles between the academy and home
- The academy says it provides more detailed management and attention.
Output must be valid JSON:

{{
  "sections": {{
    "conclude": {{
      "id": "conclude",
      "title": "마무리",
      "closing": [
        {{
          "label": "추천 활동",
          "items": [
              {{ "label": "...", "detail": "..." }}       
            ]
        }},
        {{
          "label": "온라인·도서 강화 방향",
          "items": [
              {{ "label": "...", "detail": "..." }}
          ]
        }}
      ],
      "finalize": {{
        "label": "마무리 멘트",
        "content": "..."
      }}
    }}
  }}
}}

Below is the information required for generating the counseling script.

[Case Code]
{case_code}

[Case Guides]
{case_guideline}

[Student Data]
{summary_str}
"""

# === 각 영역별 에이전트 생성 === # 
def get_avoided_and_overall_agent() -> LlmAgent:
    return LlmAgent(
        name="counseling_section_avoided_and_overall",
        model=LiteLlm(model=MODEL_GPT_5, response_format=first_schema),
        instruction=build_instruction_avoided_and_overall,
        description="Generates the '지양 표현' and '총평' sections of the counseling guide.",
        output_key="section_avoided_and_overall",
    )


def get_data_guide_agent() -> LlmAgent:
    return LlmAgent(
        name="counseling_section_data_guide",
        model=LiteLlm(model=MODEL_GPT_5, response_format=second_schema),
        instruction=build_instruction_data_guide,
        description="Generates the '데이터 해석 가이드' section of the counseling guide.",
        output_key="section_data_guide",
    )


def get_behavior_agent() -> LlmAgent:
    return LlmAgent(
        name="counseling_section_behavior",
        model=LiteLlm(model=MODEL_GPT_5, response_format=third_schema),
        instruction=build_instruction_behavior,
        description="Generates the '행동' section of the counseling guide.",
        output_key="section_behavior",
    )


def get_closing_agent() -> LlmAgent:
    return LlmAgent(
        name="counseling_section_closing",
        model=LiteLlm(model=MODEL_GPT_5, response_format=fourth_schema),
        instruction=build_instruction_closing,
        description="Generates the '마무리' section of the counseling guide.",
        output_key="section_closing",
    )

# === (현재 사용안함, Fallback용) 최종 상담 가이드 생성 에이전트 === # 
def get_counseling_generator_agent() -> LlmAgent:
    """
    Create counseling generator agent that uses outputs from upstream agents.

    - Uses case_guides.yaml as the canonical case guideline source.
    - At runtime, reads `result` from session state to determine case_code,
      extracts only that case's rules block from the YAML, and injects it
      under the [Case Guides] section.
    - Also injects {result} and {summary} from session state into the prompt.
    """

    async def build_instruction(readonly_ctx: ReadonlyContext) -> str:
        """
        Build final monolithic instruction using the shared counseling context.

        섹션별 에이전트를 병렬화 하기 위해서 핵심 컨텍스트 구축.
        """
        context = await build_counseling_base_context(readonly_ctx)
        case_guideline = context["case_guideline"]

        # 1) Inject the case guideline into the template so it's no longer a
        #    {VAR} placeholder and won't be touched by state injection.
        template = COUNSELING_GENERATOR_PROMPT.replace("{CASE_GUIDES_YAML}", case_guideline)

        # 2) Ask ADK's inject_session_state to populate {result} and {summary}
        #    (and any other state-backed placeholders) from the session.
        final_instruction = await inject_session_state(template, readonly_ctx)
        return final_instruction

    # Log the final, runtime-injected instruction just before model call
    # Signature must match BaseLlmFlow._handle_before_model_callback:
    #   callback(callback_context=..., llm_request=...)
    def _before_model_log(callback_context: CallbackContext, llm_request: LlmRequest):
        # Start performance tracking
        tracker = get_tracker()
        tracker.start("counseling_generator_agent")
        logger.info("📝 Counseling Generator Agent: Starting guide generation (monolithic)...")

        # Debug logging if enabled
        if os.getenv("PROMPT_DEBUG", "0") != "1":
            return None
        try:
            project_root = os.path.abspath(os.path.dirname(__file__) + "/../../..")
            debug_dir = os.path.join(project_root, "output", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_instruction = llm_request.config.system_instruction or ""
            with open(os.path.join(debug_dir, f"counseling_prompt_final_{ts}.txt"), "w", encoding="utf-8") as f:
                f.write(final_instruction)
        except Exception as e:
            # Best-effort logging; don't break execution
            print(f"[PROMPT_DEBUG] Failed to write final instruction: {e}")

    def _after_model_log(callback_context: CallbackContext, llm_response):
        """Track end time and log performance summary."""
        tracker = get_tracker()
        duration = tracker.end("counseling_generator_agent")
        logger.info(f"📝 Counseling Generator Agent: Completed in {duration:.2f}s")

        # Log overall performance summary
        log_performance_summary()

    return LlmAgent(
        name="counseling_generator_agent",
        model=LiteLlm(model=MODEL_GPT_5),
        instruction=build_instruction,
        description="Generates a counseling guide based on the case guideline and raw data (monolithic single call).",
        output_key="generated_counseling_guide",
        before_model_callback=_before_model_log,
        after_model_callback=_after_model_log,
    )

# === (현재 사용) 섹션별 결과 병합 함수 === # 
def _merge_sections_from_state(state: dict) -> dict:
    """Merge section-wise JSON outputs from session state into a final guide dict.
    
    최종적으로 다음과 같은 구조를 만든다:
        {
          "sections": {
            "avoid": {...},
            "summary": {...},
            "guide": {...},
            "behavior": {...},
            "conclude": {...}
          }
        }
    """
    def _ensure_obj(value, section_name: str) -> dict:
        if value is None:
            raise ValueError(f"Missing section output for {section_name}")
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception as e:
                raise ValueError(f"Failed to parse JSON for {section_name}: {e}") from e
        raise ValueError(f"Unexpected type for {section_name}: {type(value)}")

    avoided_and_overall = _ensure_obj(
        state.get("section_avoided_and_overall"), "section_avoided_and_overall"
    )
    data_guide = _ensure_obj(
        state.get("section_data_guide"), "section_data_guide"
    )
    behavior = _ensure_obj(
        state.get("section_behavior"), "section_behavior"
    )
    closing = _ensure_obj(state.get("section_closing"), "section_closing")

    merged_sections: dict = {}

    # 각 섹션 에이전트의 결과에서 "sections" 딕셔너리만 꺼내서 단순 병합
    for payload in (avoided_and_overall, data_guide, behavior, closing):
        if not isinstance(payload, dict):
            continue
        sections_obj = payload.get("sections")
        if not isinstance(sections_obj, dict):
            continue
        # 단순 merge: 뒤에 오는 값이 앞의 값을 덮어씀 (충돌 날 일은 거의 없음)
        merged_sections.update(sections_obj)

    return {"sections": merged_sections}

# === (현재 사용) 섹션별 결과 병합 베이스 에이전트 === # 
class MergeCounselingSectionsAgent(BaseAgent):
    """Pure-Python agent that merges section outputs into the final 5-section JSON."""

    output_key: str = "generated_counseling_guide"

    async def _run_async_impl(self, ctx):
        tracker = get_tracker()
        tracker.start("counseling_sections_merge")
        state = ctx.session.state
        try:
            # Try to merge section outputs from session state.
            # `merged` is a pure Python dict representing the final JSON structure.
            merged = _merge_sections_from_state(state)

            # For event streaming/logging we still serialize to a pretty JSON string,
            # but in session.state we now store the dict itself so downstream
            final_json = json.dumps(merged, ensure_ascii=False, indent=2)

            # Prepare state delta and content.
            actions = EventActions()
            # Store as dict (JSON object) instead of serialized string.
            actions.state_delta[self.output_key] = merged
            content = types.Content(parts=[types.Part.from_text(text=final_json)])

            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=content,
                actions=actions,
            )
            # Yield a single event containing the merged JSON and state delta.
            yield event

            duration = tracker.end("counseling_sections_merge")
            logger.info(
                "🧩 Counseling Sections Merge: Completed in %.2fs", duration
            )
            # Log overall performance summary for the full parallel pipeline.
            log_performance_summary()
            return
        except Exception as merge_error:
            tracker.end("counseling_sections_merge")
            logger.error(
                "Failed to merge counseling sections: %s",
                merge_error,
            )
            # Offline policy: do not fall back to legacy monolithic prompt.
            # Propagate the error so the client can see that merging failed.
            raise


# Instantiate section agents and the parallel + merge pipeline.
section_avoided_and_overall_agent = get_avoided_and_overall_agent()
section_data_guide_agent = get_data_guide_agent()
section_behavior_agent = get_behavior_agent()
section_closing_agent = get_closing_agent()


def _before_sections_parallel(callback_context: CallbackContext):
    tracker = get_tracker()
    tracker.start("counseling_sections_parallel")
    logger.info(
        "🧩 Counseling Sections Parallel: Starting parallel section generation..."
    )


def _after_sections_parallel(callback_context: CallbackContext):
    tracker = get_tracker()
    duration = tracker.end("counseling_sections_parallel")
    logger.info(
        "🧩 Counseling Sections Parallel: Completed in %.2fs", duration
    )


counseling_sections_parallel_agent = ParallelAgent(
    name="counseling_sections_parallel_agent",
    sub_agents=[
        section_avoided_and_overall_agent,
        section_data_guide_agent,
        section_behavior_agent,
        section_closing_agent,
    ],
    description="Runs counseling sections (지양+총평, 데이터 해석, 행동, 마무리) in parallel.",
    before_agent_callback=_before_sections_parallel,
    after_agent_callback=_after_sections_parallel,
)

counseling_parallel_agent = SequentialAgent(
    name="counseling_parallel_counseling_agent",
    description=(
        "Executes the CANB counseling pipeline for sections: "
        "parallel section generators then pure-Python merge into a final 5-section JSON."
    ),
    sub_agents=[
        counseling_sections_parallel_agent,
        MergeCounselingSectionsAgent(name="counseling_sections_merger"),
    ],
)