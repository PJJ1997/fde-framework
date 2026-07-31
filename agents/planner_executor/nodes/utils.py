"""Shared utility functions for nodes."""
import json
import logging
from typing import Dict

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


def build_tools_description(tools: Dict[str, StructuredTool]) -> str:
    """Build formatted tool descriptions with parameters."""
    tool_descriptions = []
    for tool_name, tool in tools.items():
        desc = f"- {tool_name}: {tool.description}"

        # Add parameter information from args_schema
        if tool.args_schema:
            params = []
            schema = tool.args_schema.model_json_schema()
            properties = schema.get("properties", {})
            required = schema.get("required", [])

            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "any")
                param_desc = param_info.get("description", "")
                is_required = param_name in required
                req_mark = "必填" if is_required else "可选"
                params.append(f"    - {param_name} ({param_type}, {req_mark}): {param_desc}")

            if params:
                desc += "\n" + "\n".join(params)

        tool_descriptions.append(desc)

    return "\n".join(tool_descriptions)


def clean_json_response(response_text: str) -> str:
    """Remove markdown code fences from JSON response."""
    cleaned = response_text.strip()
    
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    
    return cleaned


def extract_final_answer(step_results: list) -> str:
    """Extract user-friendly final answer from step results."""
    if not step_results:
        return ""

    # Get the last successful result
    last_result = step_results[-1]
    if last_result.success and "result" in last_result.result:
        final_value = last_result.result["result"]
        return str(final_value)

    return ""
