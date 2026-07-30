"""Node functions for Planner-Executor-Reviewer architecture."""
import asyncio
import json
from typing import Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from tools.executor import executor
from context import context_manager
from .schemas import (
    ExecutionPlan,
    PlannerState,
    ReviewDecision,
    StepResult,
)


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
        
        # System prompt
        system_prompt = f"""你是一个智能规划助手。根据用户目标和可用工具,生成结构化的执行计划。

可用工具:
{tools_text}

输出格式(严格JSON):
{{
  "goal": "用户目标描述",
  "steps": [
    {{
      "step_id": "step_1",
      "description": "步骤描述",
      "tool_name": "工具名称",
      "arguments": {{"arg1": "value1"}},
      "expected_result": "预期结果"
    }}
  ]
}}

重要规则:
1. step_id 必须唯一,按顺序命名: step_1, step_2, ...
2. tool_name 必须是可用工具之一
3. arguments 必须严格匹配工具的参数定义(参数名称和类型)
4. 如果用户未提供必需的信息:
   - 优先从对话历史中提取(如"这个订单"指代之前创建的订单ID)
   - 如果历史中也没有,使用合理的示例值,并在 description 中说明
5. 只输出JSON,不要其他解释

示例1: 用户说"创建订单",但未提供具体信息
- 使用示例值: customer_name="张三", product_name="示例产品", quantity=1, price=100.0, address="示例地址"
- description: "使用示例值创建订单(用户未提供具体信息)"

示例2: 对话历史显示刚创建了订单ORD-1001,用户说"查看这个订单"
- 从历史中提取: order_id="ORD-1001"
- description: "查询订单ORD-1001的详细信息"
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
            
            # Parse JSON
            plan_dict = json.loads(plan_json)
            plan = ExecutionPlan(**plan_dict)
            
            return {
                "plan": plan,
                "plan_json": plan_json,
                "current_step_index": 0,
                "step_results": [],
                "iteration_count": iteration + 1,
            }
        except Exception as e:
            # Fallback: create a simple error response
            return {
                "plan": None,
                "plan_json": None,
                "review_decision": ReviewDecision.FAIL,
                "review_feedback": f"规划失败: {str(e)}",
                "final_content": f"抱歉,无法生成执行计划: {str(e)}",
            }

    def executor(self, state: PlannerState) -> dict:
        """Executor node: Execute all steps in the plan sequentially."""
        plan = state.get("plan")
        if not plan:
            return {
                "review_decision": ReviewDecision.FAIL,
                "review_feedback": "没有可执行的计划",
                "final_content": "执行失败: 没有可执行的计划",
            }
        
        session_id = state.get("session_id", "")
        step_results = []
        
        # Execute each step
        for step in plan.steps:
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

        return {
            "step_results": step_results,
            "current_step_index": len(step_results),
        }

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
        plan = state.get("plan")
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

        # Check if plan exists
        if not plan:
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
{plan.model_dump_json(indent=2)}

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

            return {
                "review_decision": decision,
                "review_feedback": feedback,
                "final_content": final_content,
            }

        except Exception as e:
            # Fallback: simple logic
            if all_success:
                final_answer = self._extract_final_answer(step_results)
                return {
                    "review_decision": ReviewDecision.PASS,
                    "review_feedback": "所有步骤执行成功",
                    "final_content": final_answer if final_answer else "任务完成！",
                }
            else:
                return {
                    "review_decision": ReviewDecision.REPLAN,
                    "review_feedback": f"部分步骤失败,需要重新规划。错误: {str(e)}",
                    "final_content": None,
                }

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
