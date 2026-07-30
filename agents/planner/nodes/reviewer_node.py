"""Reviewer node for evaluating execution results."""
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ..schemas import PlannerState, ReviewDecision, ReviewResult
from .utils import clean_json_response, extract_final_answer

logger = logging.getLogger(__name__)


class ReviewerNode:
    """Reviewer node: Evaluate execution results."""
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
    
    def _build_results_summary(self, step_results: list) -> tuple[str, bool]:
        """Build results summary text and check if all succeeded.
        
        Returns:
            tuple: (results_text, all_success)
        """
        results_summary = []
        all_success = True
        
        for result in step_results:
            status = "✓" if result.success else "✗"
            results_summary.append(f"{status} {result.step_id} ({result.tool_name}): {result.message}")
            if not result.success:
                all_success = False
        
        return "\n".join(results_summary), all_success
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for reviewer."""
        return """你是一个执行结果评审员。评估计划执行结果是否达到用户目标。

你必须返回一个JSON对象:
{
  "decision": "PASS" | "REPLAN" | "FAIL",
  "feedback": "详细反馈"
}

决策规则:
1. PASS - 所有步骤成功,用户目标已达成
2. REPLAN - 部分步骤失败或结果不符合预期,需要重新规划
3. FAIL - 无法完成任务,不可恢复的错误

只输出JSON,不要其他解释。"""
    
    def _build_user_message(self, user_goal: str, planner_result, results_text: str) -> str:
        """Build user message for reviewer."""
        return f"""用户目标: {user_goal}

执行计划:
{json.dumps({"goal": planner_result.goal, "steps": [s.model_dump() for s in planner_result.steps]}, ensure_ascii=False, indent=2)}

执行结果:
{results_text}

请评估执行结果。"""
    
    def _call_llm_with_fallback(self, messages: list) -> tuple[ReviewDecision, str]:
        """Call LLM for review with fallback to JSON parsing.
        
        Returns:
            tuple: (decision, feedback)
        """
        try:
            # Try structured output first
            structured_llm = self.llm.with_structured_output(ReviewResult)
            review_result = structured_llm.invoke(messages)
            return ReviewDecision(review_result.decision), review_result.feedback
        except Exception as struct_error:
            # Fallback to manual JSON parsing
            logger.warning(f"Structured output not supported, falling back to JSON parsing: {struct_error}")
            response = self.llm.invoke(messages)
            review_json = response.content.strip()
            
            # Remove markdown code fences if present
            review_json = clean_json_response(review_json)
            
            # Parse and validate with Pydantic
            review_dict = json.loads(review_json)
            review_result = ReviewResult(**review_dict)
            return ReviewDecision(review_result.decision), review_result.feedback
    
    def __call__(self, state: PlannerState) -> dict:
        """Evaluate execution results.

        Makes one of three decisions:
        - PASS: All steps succeeded, goal achieved
        - REPLAN: Some steps failed or results don't meet expectations
        - FAIL: Unrecoverable error or max iterations reached
        """
        # Extract state variables
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

        try:
            # Build results summary
            results_text, all_success = self._build_results_summary(step_results)
            
            # Build prompts and call LLM
            system_prompt = self._build_system_prompt()
            user_message = self._build_user_message(user_goal, planner_result, results_text)
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ]
            
            decision, feedback = self._call_llm_with_fallback(messages)

            # Build final content - user-friendly output only
            if decision == ReviewDecision.PASS:
                final_answer = extract_final_answer(step_results)
                final_content = final_answer if final_answer else feedback
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
                final_answer = extract_final_answer(step_results)
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
