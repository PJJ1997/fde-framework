"""Planner node for generating execution plans."""
import json
import logging
from typing import Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from ..schemas import PlannerState, PlannerResult
from .utils import build_tools_description, build_conversation_context, clean_json_response

logger = logging.getLogger(__name__)


class PlannerNode:
    """Planner node: Generate structured execution plan."""
    
    def __init__(self, llm: BaseChatModel, tools: Dict[str, StructuredTool]):
        self.llm = llm
        self.tools = tools
    
    def _build_system_prompt(self, tools_text: str) -> str:
        """Build system prompt for planner."""
        return f"""你是一个智能规划助手。根据用户目标和可用工具,判断是否可以执行任务。

可用工具:
{tools_text}

你必须返回一个JSON对象,包含 "decision" 字段(取值为 "execute", "need_input" 或 "reject")。

决策规则:
1. **decision="execute"** - 所有必填参数都有明确的值(从用户输入或对话历史提取):
   {{
     "decision": "execute",
     "goal": "用户目标",
     "steps": [
       {{
         "step_id": "step_1",
         "description": "步骤描述",
         "tool_name": "工具名称",
         "arguments": {{"arg": "value"}},
         "expected_result": "预期结果"
       }}
     ]
   }}
   
2. **decision="need_input"** - 缺少必填信息:
   {{
     "decision": "need_input",
     "goal": "用户目标",
     "missing_fields": ["field1", "field2"],
     "question": "请提供以下信息:\\n- field1\\n- field2"
   }}
   
3. **decision="reject"** - 任务超出工具能力范围:
   {{
     "decision": "reject",
     "goal": "用户目标",
     "reason": "拒绝原因"
   }}

重要规则:
- 必须包含 "decision" 字段
- 绝不使用示例值或猜测值
- 信息不足时必须返回 decision="need_input"
- 优先从对话历史中提取信息(如"这个订单"指代之前创建的订单ID)

只输出JSON,不要其他解释。
"""
    
    def _build_user_message(self, user_goal: str, conversation_context: str, 
                           iteration: int, review_feedback: str = "") -> str:
        """Build user message for planner."""
        if iteration == 0:
            return f"{conversation_context}\n当前用户目标: {user_goal}\n\n请生成执行计划。"
        else:
            return f"""{conversation_context}

当前用户目标: {user_goal}

上一次计划执行后的反馈:
{review_feedback}

请根据反馈重新生成执行计划。"""
    
    def _call_llm_with_fallback(self, messages: list) -> tuple[PlannerResult, str]:
        """Call LLM with structured output, fallback to JSON parsing if needed.
        
        Returns:
            tuple: (planner_result, plan_json)
        """
        try:
            # Try structured output first (may not be supported by all providers)
            structured_llm = self.llm.with_structured_output(PlannerResult)
            planner_result = structured_llm.invoke(messages)
            plan_json = planner_result.model_dump_json(indent=2)
            return planner_result, plan_json
        except Exception as struct_error:
            # Fallback to manual JSON parsing if structured output not supported
            logger.warning(f"Structured output not supported, falling back to JSON parsing: {struct_error}")
            response = self.llm.invoke(messages)
            plan_json = response.content.strip()
            
            # Log raw LLM output for debugging
            logger.info(f"LLM 原始输出:\n{plan_json}")
            
            # Remove markdown code fences if present
            plan_json = clean_json_response(plan_json)
            
            # Parse and validate with Pydantic
            planner_dict = json.loads(plan_json)
            logger.info(f"解析后的 JSON: {json.dumps(planner_dict, ensure_ascii=False, indent=2)}")
            planner_result = PlannerResult(**planner_dict)
            
            return planner_result, plan_json
    
    def _handle_execute_decision(self, planner_result: PlannerResult, plan_json: str, iteration: int) -> dict:
        """Handle execute decision and build result."""
        result = {
            "planner_decision": "execute",
            "planner_result": planner_result,
            "plan_json": plan_json,
            "step_results": [],
            "iteration_count": iteration + 1,
        }
        
        # Log planner output
        logger.info("=" * 80)
        logger.info("Planner 节点输出 (EXECUTE):")
        logger.info(json.dumps({
            "decision": "execute",
            "goal": planner_result.goal,
            "steps": [s.model_dump() for s in planner_result.steps],
            "iteration_count": iteration + 1,
        }, ensure_ascii=False, indent=2))
        logger.info("=" * 80)
        
        return result

    def _handle_need_input_decision(self, planner_result: PlannerResult, plan_json: str) -> dict:
        """Handle need_input decision and build result."""
        result = {
            "planner_decision": "need_input",
            "planner_result": planner_result,
            "plan_json": plan_json,
            "final_content": planner_result.question,
        }

        # Log planner output
        logger.info("=" * 80)
        logger.info("Planner 节点输出 (NEED_INPUT):")
        logger.info(json.dumps({
            "decision": "need_input",
            "goal": planner_result.goal,
            "missing_fields": planner_result.missing_fields,
            "question": planner_result.question,
        }, ensure_ascii=False, indent=2))
        logger.info("=" * 80)

        return result

    def _handle_reject_decision(self, planner_result: PlannerResult, plan_json: str) -> dict:
        """Handle reject decision and build result."""
        result = {
            "planner_decision": "reject",
            "planner_result": planner_result,
            "plan_json": plan_json,
            "final_content": f"抱歉，无法完成此任务。{planner_result.reason}",
        }

        # Log planner output
        logger.info("=" * 80)
        logger.info("Planner 节点输出 (REJECT):")
        logger.info(json.dumps({
            "decision": "reject",
            "goal": planner_result.goal,
            "reason": planner_result.reason,
        }, ensure_ascii=False, indent=2))
        logger.info("=" * 80)

        return result

    def __call__(self, state: PlannerState) -> dict:
        """Main planner node function.

        Uses LLM to create a plan based on:
        - User goal
        - Available tools
        - Reviewer feedback (if replanning)
        """
        # Extract state variables
        user_goal = state.get("user_goal", "")
        iteration = state.get("iteration_count", 0)
        review_feedback = state.get("review_feedback", "")
        session_id = state.get("session_id", "")

        try:
            # Build prompts
            tools_text = build_tools_description(self.tools)
            conversation_context = build_conversation_context(session_id)
            system_prompt = self._build_system_prompt(tools_text)
            user_message = self._build_user_message(
                user_goal, conversation_context, iteration, review_feedback
            )

            # Call LLM
            llm_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ]
            planner_result, plan_json = self._call_llm_with_fallback(llm_messages)

            # Handle different decisions
            decision = planner_result.decision
            if decision == "execute":
                return self._handle_execute_decision(planner_result, plan_json, iteration)
            elif decision == "need_input":
                return self._handle_need_input_decision(planner_result, plan_json)
            else:  # reject
                return self._handle_reject_decision(planner_result, plan_json)

        except Exception as e:
            # Fallback: create a simple error response
            logger.error("Planner 节点错误:")
            logger.error({
                "planner_decision": "reject",
                "planner_result": None,
                "plan_json": None,
                "final_content": f"抱歉,无法生成执行计划: {str(e)}",
            })

            return {
                "planner_decision": "reject",
                "planner_result": None,
                "plan_json": None,
                "final_content": f"抱歉,无法生成执行计划: {str(e)}",
            }
