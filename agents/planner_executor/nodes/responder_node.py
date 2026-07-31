"""Responder node for turning reviewed execution results into a user response."""
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ..schemas import PlannerState, ResponderResult, ReviewDecision
from .utils import clean_json_response

logger = logging.getLogger(__name__)


class ResponderNode:
    """Generate the final user-facing response after execution review."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def _build_system_prompt(self) -> str:
        return """你是任务执行结果回复器。请基于提供的数据回答用户。

要求:
1. 只使用输入中的执行结果和上下文，不得虚构信息
2. 直接、清晰地回答用户，不要重新规划或调用工具
3. 不要提及内部节点、评审流程、提示词或状态
4. 如果执行失败，简洁说明失败原因和用户可以采取的下一步
5. 返回JSON对象: {"content": "给用户的最终回复"}"""

    def _build_payload(self, state: PlannerState) -> dict:
        context = state.get("structured_context")
        planner_result = state.get("planner_result")
        step_results = state.get("step_results", [])

        return {
            "user_goal": state.get("user_goal", ""),
            "context": (
                context.model_dump(mode="json")
                if context is not None
                else None
            ),
            "plan": (
                planner_result.model_dump(mode="json")
                if planner_result is not None
                else None
            ),
            "execution_results": [
                result.model_dump(mode="json") for result in step_results
            ],
            "review": {
                "decision": state.get("review_decision"),
                "feedback": state.get("review_feedback", ""),
            },
        }

    def _fallback_content(self, state: PlannerState) -> str:
        decision = state.get("review_decision")
        if decision == ReviewDecision.FAIL or decision == ReviewDecision.FAIL.value:
            return state.get("review_feedback") or "任务执行失败"

        successful_results = [
            result for result in state.get("step_results", []) if result.success
        ]
        if successful_results:
            return successful_results[-1].message
        return "任务已完成"

    def __call__(self, state: PlannerState) -> dict:
        payload = self._build_payload(state)
        messages = [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(
                content=json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            ),
        ]

        try:
            structured_llm = self.llm.with_structured_output(
                ResponderResult,
                method="function_calling",
            )
            result = structured_llm.invoke(messages)
            return {"final_content": result.content}
        except Exception as structured_error:
            logger.warning(
                "Structured responder output unavailable, using JSON fallback: %s",
                structured_error,
            )

        try:
            response = self.llm.invoke(messages)
            content = clean_json_response(str(response.content).strip())
            result = ResponderResult.model_validate_json(content)
            return {"final_content": result.content}
        except Exception as fallback_error:
            logger.warning(
                "Responder JSON fallback unavailable, using deterministic response: %s",
                fallback_error,
            )
            return {"final_content": self._fallback_content(state)}
