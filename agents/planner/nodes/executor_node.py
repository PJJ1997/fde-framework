"""Executor node for executing planned steps."""
import json
import logging
from typing import Dict

from langchain_core.tools import StructuredTool

from tools.executor import executor
from ..schemas import PlannerState, StepResult, ReviewDecision

logger = logging.getLogger(__name__)


class ExecutorNode:
    """Executor node: Execute all steps in the plan sequentially."""
    
    def __init__(self, tools: Dict[str, StructuredTool]):
        self.tools = tools
    
    def __call__(self, state: PlannerState) -> dict:
        """Execute all steps in the plan sequentially."""
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
            
            tool = self.tools[tool_name]
            
            try:
                # Execute tool
                result = executor.execute_tool(
                    tool=tool,
                    args=step.arguments,
                    session_id=session_id
                )
                
                # Extract user-friendly message
                if isinstance(result, dict):
                    # Try to get a concise message
                    if "message" in result:
                        message = result["message"]
                    elif "result" in result:
                        message = f"结果: {result['result']}"
                    else:
                        message = str(result)
                else:
                    message = str(result)
                
                step_results.append(StepResult(
                    step_id=step.step_id,
                    tool_name=tool_name,
                    success=True,
                    result=result if isinstance(result, dict) else {"output": result},
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
            "results": [
                {
                    "step_id": sr.step_id,
                    "tool_name": sr.tool_name,
                    "success": sr.success,
                    "message": sr.message
                }
                for sr in step_results
            ]
        }, ensure_ascii=False, indent=2))
        logger.info("=" * 80)
        
        return result
