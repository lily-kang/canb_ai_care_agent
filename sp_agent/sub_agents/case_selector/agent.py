import json
import logging
import os

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from .prompt import CASE_SELECTOR_PROMPT
from sp_agent.tools import (
    load_text_file,
    substitute_variables,
    get_feature_and_raw_from_state,
)
from sp_agent.utils.performance_logger import get_tracker

logger = logging.getLogger(__name__)
load_dotenv()


MODEL_GPT_4O = "openai/gpt-4.1"
MODEL_GEMINI = "gemini-2.5-flash"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Load static knowledge once at import time.
case_criteria_md = load_text_file("sp_agent/knowledge/CANB_CARE_Case_Classification.md")


async def build_case_selector_instruction(readonly_ctx: ReadonlyContext) -> str:
    """
    Build instruction for case_selector_agent using per-session feature_json.

    - CASE_CRITERIA_MD: static markdown from knowledge file.
    - FEATURE_JSON: per-session JSON blob from session.state["feature_json"].
    """
    state = readonly_ctx.session.state
    feature_json, _ = get_feature_and_raw_from_state(state)

    if feature_json is None:
        feature_text = "[세션에 feature_json 없음]"
    elif isinstance(feature_json, str):
        feature_text = feature_json
    else:
        try:
            feature_text = json.dumps(feature_json, ensure_ascii=False, indent=2)
        except Exception:
            feature_text = "[feature_json 직렬화 실패]"

    instruction = substitute_variables(
        CASE_SELECTOR_PROMPT,
        CASE_CRITERIA_MD=case_criteria_md,
        FEATURE_JSON=feature_text,
    )
    return instruction


# Performance tracking callbacks
def _before_case_selector(callback_context, llm_request):
    """Track start time for case selector."""
    tracker = get_tracker()
    tracker.start("case_selector_agent")
    logger.info("🔍 Case Selector Agent: Starting case selection...")


def _after_case_selector(callback_context, llm_response):
    """Track end time for case selector."""
    tracker = get_tracker()
    duration = tracker.end("case_selector_agent")
    logger.info(f"🔍 Case Selector Agent: Completed in {duration:.2f}s")


case_selector_agent = LlmAgent(
    name="case_selector_agent",
    model=LiteLlm(
        model=MODEL_GPT_4O,
        api_key=OPENAI_API_KEY,
    ),
    instruction=build_case_selector_instruction,
    description="Selects the closest case based on the feature data and CANB_CARE_상담 CASE 분류근거.md file.",
    output_key="result",
    before_model_callback=_before_case_selector,
    after_model_callback=_after_case_selector,
)
