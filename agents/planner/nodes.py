"""Node functions for Planner-Executor-Reviewer architecture."""
import asyncio
import json
import logging
from typing import Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from tools.executor import executor
from context import context_manager
from .schemas import (
    PlannerState,
    PlannerDecision,
    PlannerResult,
    ReviewDecision,
    StepResult,
)

logger = logging.getLogger(__name__)


class PlannerNodes:
    """Node functions for Planner-Executor-Reviewer workflow."""

    def __init__(self, llm: BaseChatModel, tools: Dict[str, StructuredTool]):
        self.llm = llm
        self.tools = tools

    def planner(self, state: PlannerState) -> dict:
        """Planner node: Generate structured execution plan.
        
        Uses LLM to create a plan based on:
        - User goal
        - Available tools
        - Reviewer feedback (if replanning)
        """
        user_goal = state.get("user_goal", "")
        iteration = state.get("iteration_count", 0)
        review_feedback = state.get("review_feedback", "")
        session_id = state.get("session_id", "")
        
        # Build tool descriptions with parameters
        tool_descriptions = []
        for tool_name, tool in self.tools.items():
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

        tools_text = "\n".join(tool_descriptions)
        
        # System prompt with new decision logic
        system_prompt = f"""你是一个智能规划助手。根据用户目标和可用工具,判断是否可以执行任务。

可用工具:
{tools_text}

输出格式(严格JSON,包含decision字段):
当 decision=execute 时:
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

当 decision=need_input 时:
{{
  "decision": "need_input",
  "goal": "用户目标",
  "missing_fields": ["field1", "field2"],
  "question": "请提供以下信息:\\n- field1\\n- field2"
}}

当 decision=reject 时:
{{
  "decision": "reject",
  "goal": "用户目标",
  "reason": "拒绝原因"
}}

决策规则:
1. execute - 所有必填参数都有值(从用户输入或对话历史提取)
2. need_input - 缺少必填信息,列出missing_fields并用question询问用户
3. reject - 任务超出工具能力范围

重要: 绝不使用示例值或猜测值! 信息不足时必须返回need_input。
只输出JSON,不要其他解释。
"""

        # Build conversation history context from context_manager
        conversation_context = ""
        if session_id:
            conversations = context_manager.get_conversations(session_id)
            # Get last 5 conversations (10 messages) for context
            if conversations and len(conversations) > 0:
                recent_convs = conversations[-10:] if len(conversations) > 10 else conversations
                conv_lines = []
                for conv in recent_convs:
                    role = conv.get("role", "user")
                    content = conv.get("content", "")
                    role_name = "用户" if role == "user" else "助手"
                    # Limit content length to avoid token overflow
                    content_preview = content[:200] if len(content) > 200 else content
                    conv_lines.append(f"{role_name}: {content_preview}")

                if conv_lines:
                    conversation_context = "\n最近对话:\n" + "\n".join(conv_lines) + "\n"

        # User message
        if iteration == 0:
            user_message = f"{conversation_context}\n当前用户目标: {user_goal}\n\n请生成执行计划。"
        else:
            user_message = f"""{conversation_context}

当前用户目标: {user_goal}

上一次计划执行后的反馈:
{review_feedback}

请根据反馈重新生成执行计划。"""

        # Call LLM
        llm_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        try:
            response = self.llm.invoke(llm_messages)
            plan_json = response.content.strip()
            
            # Remove markdown code fences if present
            if plan_json.startswith("```"):
                lines = plan_json.split("\n")
                plan_json = "\n".join(lines[1:-1]) if len(lines) > 2 else plan_json
                plan_json = plan_json.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON and create PlannerResult
            planner_dict = json.loads(plan_json)
            planner_result = PlannerResult(**planner_dict)

            decision = planner_result.decision

            # Handle different decisions
            if decision == "execute":
                result = {
                    "planner_decision": decision,
                    "planner_result": planner_result,
                    "plan_json": plan_json,
                    "step_results": [],
                    "iteration_count": iteration + 1,
                }

                # Log planner output
                logger.info("=" * 80)
                logger.info("Planner 节点输出 (EXECUTE):")
                logger.info(json.dumps({
                    "decision": decision,
                    "goal": planner_result.goal,
                    "steps": [s.model_dump() for s in planner_result.steps],
                    "iteration_count": iteration + 1,
                }, ensure_ascii=False, indent=2))
                logger.info("=" * 80)

                return result

            elif decision == "need_input":
                # Need user input - stop here and ask question
                result = {
                    "planner_decision": decision,
                    "planner_result": planner_result,
                    "plan_json": plan_json,
                    "final_content": planner_result.question,
                }

                # Log planner output
                logger.info("=" * 80)
                logger.info("Planner 节点输出 (NEED_INPUT):")
                logger.info(json.dumps({
                    "decision": decision,
                    "goal": planner_result.goal,
                    "missing_fields": planner_result.missing_fields,
                    "question": planner_result.question,
                }, ensure_ascii=False, indent=2))
                logger.info("=" * 80)

                return result

            else:  # reject
                # Reject the request
                result = {
                    "planner_decision": decision,
                    "planner_result": planner_result,
                    "plan_json": plan_json,
                    "final_content": f"抱歉，无法完成此任务。{planner_result.reason}",
                }

                # Log planner output
                logger.info("=" * 80)
                logger.info("Planner 节点输出 (REJECT):")
                logger.info(json.dumps({
                    "decision": decision,
                    "goal": planner_result.goal,
                    "reason": planner_result.reason,
                }, ensure_ascii=False, indent=2))
                logger.info("=" * 80)

                return result

        except Exception as e:
            # Fallback: create a simple error response
            error_result = {
                "planner_decision": "reject",
                "planner_result": None,
                "plan_json": None,
                "final_content": f"抱歉,无法生成执行计划: {str(e)}",
            }

            # Log error
            logger.error("=" * 80)
            logger.error("Planner 节点错误:")
            logger.error(json.dumps(error_result, ensure_ascii=False, indent=2))
            logger.error("=" * 80)

            return error_result

    def executor(self, state: PlannerState) -> dict:
        """Executor node: Execute all steps in the plan sequentially."""
        planner_result = state.get("planner_result")
        if not planner_result or not planner_result.steps:
            return {
                "review_decision": ReviewDecision.FAIL,
                "review_feedback": "没有可执行的计划",
                "final_content": "执行失败: 没有可执行的计划",
            }

        session_id = state.get("session_id", "")
        step_results = []

        # Execute each step
        for step in planner_result.steps:
            tool_name = step.tool_name
            
            # Check if tool exists
            if tool_name not in self.tools:
                step_results.append(StepResult(
                    step_id=step.step_id,
                    tool_name=tool_name,
                    success=False,
                    result={"error": f"工具 '{tool_name}' 不存在"},
                    message=f"错误: 工具 '{tool_name}' 不存在"
                ))
                continue
            
            # Execute tool
            try:
                tool = self.tools[tool_name]
                result = asyncio.run(
                    executor.execute(
                        tool,
                        step.arguments,
                        context={"session_id": session_id}
                    )
                )

                # Check result
                success = "error" not in result

                # Extract a clean message for display
                if success:
                    # For successful results, extract the main value
                    if "result" in result:
                        message = f"结果: {result['result']}"
                    elif "message" in result:
                        message = result["message"]
                    else:
                        message = "执行成功"
                else:
                    message = result.get("error", "执行失败")

                step_results.append(StepResult(
                    step_id=step.step_id,
                    tool_name=tool_name,
                    success=success,
                    result=result,
                    message=message
                ))

            except Exception as e:
                step_results.append(StepResult(
                    step_id=step.step_id,
                    tool_name=tool_name,
                    success=False,
                    result={"error": str(e)},
                    message=f"执行失败: {str(e)}"
                ))

        result = {
            "step_results": step_results,
        }

        # Log executor output
        logger.info("=" * 80)
        logger.info("Executor 节点输出:")
        logger.info(json.dumps({
            "total_steps": len(step_results),
            "steps": [
                {
                    "step_id": sr.step_id,
                    "tool_name": sr.tool_name,
                    "success": sr.success,
                    "message": sr.message,
                    "result": sr.result
                }
                for sr in step_results
            ]
        }, ensure_ascii=False, indent=2))
        logger.info("=" * 80)

        return result

    def _extract_final_answer(self, step_results: list) -> str:
        """Extract user-friendly final answer from step results."""
        if not step_results:
            return ""

        # Get the last successful result
        last_result = step_results[-1]
        if last_result.success and "result" in last_result.result:
            final_value = last_result.result["result"]
            return str(final_value)

        return ""

    def reviewer(self, state: PlannerState) -> dict:
        """Reviewer node: Evaluate execution results.

        Makes one of three decisions:
        - PASS: All steps succeeded, goal achieved
        - REPLAN: Some steps failed or results don't meet expectations
        - FAIL: Unrecoverable error or max iterations reached
        """
        planner_result = state.get("planner_result")
        step_results = state.get("step_results", [])
        iteration = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 3)
        user_goal = state.get("user_goal", "")

        # Check max iterations
        if iteration >= max_iterations:
            return {
                "review_decision": ReviewDecision.FAIL,
                "review_feedback": f"已达到最大迭代次数 ({max_iterations})",
                "final_content": f"抱歉,在 {max_iterations} 次尝试后仍未完成任务。",
            }

        # Check if planner_result exists
        if not planner_result:
            return {
                "review_decision": ReviewDecision.FAIL,
                "review_feedback": "没有执行计划",
                "final_content": "执行失败: 没有执行计划",
            }

        # Build results summary
        results_summary = []
        all_success = True
        for result in step_results:
            status = "✓" if result.success else "✗"
            results_summary.append(f"{status} {result.step_id} ({result.tool_name}): {result.message}")
            if not result.success:
                all_success = False

        results_text = "\n".join(results_summary)

        # Use LLM to review
        system_prompt = """你是一个执行结果评审员。评估计划执行结果是否达到用户目标。

你必须返回以下三种决策之一:
1. PASS - 所有步骤成功,用户目标已达成
2. REPLAN - 部分步骤失败或结果不符合预期,需要重新规划
3. FAIL - 无法完成任务,不可恢复的错误

输出格式(严格JSON):
{
  "decision": "PASS" | "REPLAN" | "FAIL",
  "feedback": "详细反馈,解释为什么做出这个决策"
}

只输出JSON,不要其他解释。"""

        user_message = f"""用户目标: {user_goal}

执行计划:
{json.dumps({"goal": planner_result.goal, "steps": [s.model_dump() for s in planner_result.steps]}, ensure_ascii=False, indent=2)}

执行结果:
{results_text}

请评估执行结果。"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ]
            response = self.llm.invoke(messages)
            review_json = response.content.strip()

            # Remove markdown code fences
            if review_json.startswith("```"):
                lines = review_json.split("\n")
                review_json = "\n".join(lines[1:-1]) if len(lines) > 2 else review_json
                review_json = review_json.replace("```json", "").replace("```", "").strip()

            review_dict = json.loads(review_json)
            decision = ReviewDecision(review_dict["decision"])
            feedback = review_dict["feedback"]

            # Build final content - user-friendly output only
            if decision == ReviewDecision.PASS:
                # Extract the final answer from step results
                final_answer = self._extract_final_answer(step_results)
                if final_answer:
                    final_content = final_answer
                else:
                    final_content = feedback
            elif decision == ReviewDecision.FAIL:
                final_content = f"抱歉，{feedback}"
            else:
                final_content = None  # Will replan, no final content yet

            result = {
                "review_decision": decision,
                "review_feedback": feedback,
                "final_content": final_content,
            }

            # Log reviewer output
            logger.info("=" * 80)
            logger.info("Reviewer 节点输出:")
            logger.info(json.dumps({
                "decision": decision.value,
                "feedback": feedback,
                "final_content": final_content,
            }, ensure_ascii=False, indent=2))
            logger.info("=" * 80)

            return result

        except Exception as e:
            # Fallback: simple logic
            if all_success:
                final_answer = self._extract_final_answer(step_results)
                fallback_result = {
                    "review_decision": ReviewDecision.PASS,
                    "review_feedback": "所有步骤执行成功",
                    "final_content": final_answer if final_answer else "任务完成！",
                }
            else:
                fallback_result = {
                    "review_decision": ReviewDecision.REPLAN,
                    "review_feedback": f"部分步骤失败,需要重新规划。错误: {str(e)}",
                    "final_content": None,
                }

            # Log fallback output
            logger.warning("=" * 80)
            logger.warning("Reviewer 节点 (Fallback) 输出:")
            logger.warning(json.dumps({
                "decision": fallback_result["review_decision"].value,
                "feedback": fallback_result["review_feedback"],
                "final_content": fallback_result["final_content"],
                "error": str(e)
            }, ensure_ascii=False, indent=2))
            logger.warning("=" * 80)

            return fallback_result

    @staticmethod
    def route_after_planner(state: PlannerState) -> str:
        """Conditional edge: route based on planner decision."""
        decision = state.get("planner_decision")

        if decision == "execute":
            return "executor"  # Continue to execution
        else:  # need_input or reject
            return "end"  # Stop and return to user

    @staticmethod
    def should_continue(state: PlannerState) -> str:
        """Conditional edge: route based on reviewer decision."""
        decision = state.get("review_decision")

        if decision == ReviewDecision.PASS:
            return "end"
        elif decision == ReviewDecision.FAIL:
            return "end"
        else:  # REPLAN
            return "planner"
