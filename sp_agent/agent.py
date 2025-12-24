from google.adk.agents import SequentialAgent
from .sub_agents.case_selector.agent import case_selector_agent
# from .sub_agents.parallel_agent import parallel_agent
from .sub_agents.counseling_generator.agent import (
    counseling_parallel_agent,
    get_counseling_generator_agent,
)
from .sub_agents.data_bootstrap.data import StudentDataBootstrapAgentV2

# Create counseling generator pipelines
# - `parallel_agent` outputs to "result" (case code) and "summary" (student data)
# - `counseling_parallel_agent` runs section-wise generators in parallel and merges
#   them into a single 5-section JSON under "generated_counseling_guide".
# - `get_counseling_generator_agent()` remains as monolithic fallback / legacy path.
counseling_generator_monolithic = get_counseling_generator_agent()

# Bootstrap per-student JSON (feature_json / raw_json / summary) from external APIs
student_data_bootstrap_agent = StudentDataBootstrapAgentV2(
    name="student_data_bootstrap_agent_v2",
)

root_agent = SequentialAgent(
    name="root_agent",
    description=(
        "Executes the CANB counseling pipeline: "
        "bootstrap student data from external APIs, case selection, then "
        "parallel section-wise counseling generation with final JSON merge."
    ),
    sub_agents=[
        student_data_bootstrap_agent,
        case_selector_agent,
        counseling_parallel_agent,
    ],
)