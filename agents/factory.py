"""Agent factory for creating agents by type."""
from pathlib import Path
from typing import List, Optional

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool

from agents.base import BaseAgent
from agents.react.react import ReActAgent
from agents.workflow.workflow import WorkflowAgent
from agents.planner.planner_agent import PlannerAgent

def _load_config() -> dict:
    """Load agent config from config.yml (read each time so changes take
    effect without restarting the server)."""
    config_path = Path(__file__).parent / "config.yml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_agent(
    llm: BaseChatModel,
    tools: List[StructuredTool] = None,
    agent_type: Optional[str] = None,
) -> BaseAgent:
    """Create an agent.

    Args:
        llm: LangChain LLM instance
        tools: List of LangChain StructuredTool (required for react and multi)
        agent_type: Agent type override. If None, uses the "active" value
            from agents/config.yml. Supported: "react", "workflow", "planner".

    Returns:
        BaseAgent instance
    """
    if agent_type is None:
        agent_type = _load_config()["active"]

    if agent_type == "react":
        return ReActAgent(llm, tools or [])

    if agent_type == "workflow":
        return WorkflowAgent(llm)

    if agent_type == "planner":
        return PlannerAgent(llm)

    raise ValueError(f"Unknown agent type: {agent_type}. Supported: 'react', 'workflow', 'planner'")


def get_resume_data(agent_type: Optional[str] = None) -> dict:
    """Get the default resume_data for an agent type.

    Args:
        agent_type: Agent type override. If None, uses the "active" value
            from agents/config.yml.

    Returns:
        resume_data dict, e.g. {"confirmed": True}
    """
    if agent_type is None:
        agent_type = _load_config()["active"]
    return _load_config().get("resume_data", {}).get(agent_type, {})
