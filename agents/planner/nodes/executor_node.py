"""Executor node for executing planned steps."""
import asyncio
import json
import logging
from typing import Dict

from langchain_core.tools import StructuredTool

from context.manager import ContextManager, context_manager
from tools.executor import ToolExecutor, executor
from ..schemas import PlannerState, StepResult, ReviewDecision

logger = logging.getLogger(__name__)


class ExecutorNode:
    """Executor node: Execute all steps in the plan sequentially."""
    
    def __init__(
        self,
        tools: Dict[str, StructuredTool],
        context_manager_instance: ContextManager = context_manager,
        tool_executor: ToolExecutor = executor,
    ):
        self.tools = tools
        self.context_manager = context_manager_instance
        self.tool_executor = tool_executor
    
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
                result = asyncio.run(
                    self.tool_executor.execute(
                        tool,
                        step.arguments,
                        context={"session_id": session_id},
                    )
                )
                
                # Extract user-friendly message
                if isinstance(result, dict):
                    # Try to get a concise message
                    if "message" in result:
                        message = result["message"]
                    elif "error" in result:
                        message = str(result["error"])
                    elif "result" in result:
                        message = f"结果: {result['result']}"
                    else:
                        message = str(result)
                    success = bool(
                        result.get(
                            "success",
                            "error" not in result,
                        )
                    )
                else:
                    message = str(result)
                    success = True
                
                step_results.append(StepResult(
                    step_id=step.step_id,
                    tool_name=tool_name,
                    success=success,
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
        self.context_manager.record_tool_facts(
            session_id,
            step_results,
        )
        
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
