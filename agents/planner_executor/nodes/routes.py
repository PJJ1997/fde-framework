"""Routing functions for conditional edges in the graph."""
from ..schemas import PlannerState, ReviewDecision


def route_after_planner(state: PlannerState) -> str:
    """Conditional edge: route based on planner decision."""
    decision = state.get("planner_decision", "reject")
    
    if decision == "execute":
        return "executor"
    else:
        # Both need_input and reject should end the workflow
        return "end"


def route_after_reviewer(state: PlannerState) -> str:
    """Conditional edge: route based on reviewer decision."""
    decision = state.get("review_decision")
    
    if decision == ReviewDecision.REPLAN:
        return "planner"
    return "responder"
