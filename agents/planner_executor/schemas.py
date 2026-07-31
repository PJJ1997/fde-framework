"""Schemas for Planner-Executor-Reviewer architecture."""
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from context.structured import StructuredConversationContext


class PlannerDecision(str, Enum):
    """Planner decision enum."""
    EXECUTE = "execute"      # 信息充足，可以执行
    NEED_INPUT = "need_input"  # 缺少必填信息，需要询问用户
    REJECT = "reject"         # 无法完成任务


class ReviewDecision(str, Enum):
    """Review decision enum."""
    PASS = "PASS"
    REPLAN = "REPLAN"
    FAIL = "FAIL"


class ReviewResult(BaseModel):
    """Structured review result from Reviewer."""
    decision: Literal["PASS", "REPLAN", "FAIL"] = Field(
        description="Review decision: PASS (成功), REPLAN (重新规划), FAIL (失败)"
    )
    feedback: str = Field(
        description="Detailed feedback explaining the decision"
    )


class ResponderResult(BaseModel):
    """Structured final response produced for the user."""
    content: str = Field(
        description="Final user-facing response based only on execution results"
    )


class PlanStep(BaseModel):
    """Single step in an execution plan."""
    step_id: str = Field(description="Unique step identifier, e.g., 'step_1'")
    description: str = Field(description="Human-readable description of what this step does")
    tool_name: str = Field(description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments as key-value pairs")
    expected_result: str = Field(description="Expected outcome of this step")


class PlannerResult(BaseModel):
    """Result from Planner with decision logic."""
    decision: Literal["execute", "need_input", "reject"] = Field(
        description="Planner decision: execute (可执行), need_input (需要用户输入), reject (拒绝)"
    )
    goal: str = Field(description="Overall goal to accomplish")
    steps: List[PlanStep] = Field(
        default_factory=list,
        description="Ordered list of steps to execute (only when decision=execute)"
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="List of missing required fields (only when decision=need_input)"
    )
    question: Optional[str] = Field(
        None,
        description="Question to ask user for missing info (only when decision=need_input)"
    )
    reason: Optional[str] = Field(
        None,
        description="Reason for rejection (only when decision=reject)"
    )


class StepResult(BaseModel):
    """Result from executing a single step."""
    step_id: str = Field(description="Step identifier")
    tool_name: str = Field(description="Tool that was called")
    success: bool = Field(description="Whether execution succeeded")
    result: Dict[str, Any] = Field(default_factory=dict, description="Tool output or error")
    message: str = Field(description="Human-readable result message")


class PlannerState(TypedDict, total=False):
    """State for Planner-Executor-Reviewer workflow.

    Tracks everything needed for the multi-agent loop:
    - What the user wants to do
    - Current plan
    - Execution progress
    - Results from each step
    - Reviewer feedback
    - Loop counter for max retries
    """
    # User input
    session_id: str
    messages: List[BaseMessage]
    user_goal: str  # What the user wants to accomplish
    structured_context: Optional[StructuredConversationContext]

    # Planning decision
    planner_decision: Optional[str]  # execute, need_input, reject
    planner_result: Optional[PlannerResult]  # Full planner result (contains all info)
    plan_json: Optional[str]  # Raw JSON from LLM (for debugging/logging)

    # Execution tracking
    step_results: List[StepResult]  # Results from all executed steps

    # Review
    review_decision: Optional[ReviewDecision]  # PASS, REPLAN, or FAIL
    review_feedback: Optional[str]  # Why reviewer made this decision

    # Loop control
    iteration_count: int  # How many Planner -> Executor -> Reviewer cycles
    max_iterations: int  # Safety limit to prevent infinite loops

    # Final output
    final_content: Optional[str]  # Final message to user
