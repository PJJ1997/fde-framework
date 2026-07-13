"""Chat router."""
import json
import uuid
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage
from llm import create_llm
from tools.registry import registry
from agents import create_agent, AgentInput, AgentResult
from context import context_manager
from prompts.system_prompt import build_system_prompt

router = APIRouter(prefix="/api", tags=["chat"])


def step_to_results(step: dict, session_id: str) -> list[dict]:
    """Convert a LangGraph step to AgentResult.to_dict() format.

    Unified filter: only user-facing text is sent to frontend.
    - ReAct agent: AIMessage content
    - Workflow agent: latest step_results entry
    ToolMessage, HumanMessage, and internal metadata are skipped.
    """
    results = []
    for node_output in step.values():
        if not isinstance(node_output, dict):
            continue
        # ReAct agent: extract AIMessage text content
        for msg in node_output.get("messages", []):
            if isinstance(msg, AIMessage) and msg.content:
                result = AgentResult(content=msg.content, session_id=session_id)
                results.append(result.to_dict())
        # Workflow agent: extract latest step_result entry (dict with
        # {"role": ..., "content": ...})
        step_results = node_output.get("step_results", [])
        if step_results:
            last = step_results[-1]
            text = last["content"] if isinstance(last, dict) else str(last)
            result = AgentResult(content=text, session_id=session_id)
            results.append(result.to_dict())
    return results


@router.post("/chat")
async def chat(request: Request):
    """Chat with agent."""
    body = await request.json()
    text = body.get("text", "")
    session_id = body.get("session_id", str(uuid.uuid4()))
    permissions = body.get("permissions", [])

    # Create agent via factory (registry wraps tools with executor)
    llm = create_llm()
    context = {"session_id": session_id, "permissions": permissions}
    tools = registry.get_tools(context=context)
    agent = create_agent(llm, tools)

    # Build system prompt: use caller-provided prompt, or inject actual
    # registered tools dynamically so the LLM only sees real tools.
    system_prompt = body.get("system_prompt") or build_system_prompt(tools)

    # Build context (returns LangChain messages)
    messages = context_manager.build(
        session_id=session_id,
        system_prompt=system_prompt,
        user_input=text,
        include_history=True
    )

    # Save user message (optional — workflow agents may not need text)
    if text:
        context_manager.save_user_message(session_id, text)

    # Invoke agent (returns AgentResult)
    result = await agent.invoke(AgentInput(messages=messages, session_id=session_id))

    return result.to_dict()


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


@router.get("/conversations")
async def conversations(session_id: str = Query(..., min_length=1)):
    """Get conversation history (user + assistant) for a session.

    Returns messages in newest-first order. Only user/assistant text
    content is included; system and tool messages are excluded.
    """
    messages = context_manager.get_conversations(session_id)
    return {"session_id": session_id, "conversations": messages}


@router.post("/chat_sse")
async def chat_sse(request: Request):
    """Chat with agent using SSE streaming."""
    body = await request.json()
    text = body.get("text", "")
    session_id = body.get("session_id", str(uuid.uuid4()))
    permissions = body.get("permissions", [])

    # Create agent via factory (registry wraps tools with executor)
    llm = create_llm()
    context = {"session_id": session_id, "permissions": permissions}
    tools = registry.get_tools(context=context)
    agent = create_agent(llm, tools)

    # Build system prompt with actual registered tools injected dynamically.
    system_prompt = build_system_prompt(tools)

    # Build context (returns LangChain messages)
    messages = context_manager.build(
        session_id=session_id,
        system_prompt=system_prompt,
        user_input=text,
        include_history=True
    )

    # Save user message (optional — workflow agents may not need text)
    if text:
        context_manager.save_user_message(session_id, text)

    async def generate():
        """Generate SSE events from agent stream."""
        try:
            step_count = 0

            async for step in agent.stream(AgentInput(messages=messages, session_id=session_id)):
                # Check if execution was interrupted (e.g. confirmation needed)
                if isinstance(step, AgentResult):
                    # Send AgentResult as final event
                    final_data = json.dumps(
                        step.to_dict(),
                        ensure_ascii=False,
                        default=str
                    )
                    yield f"data: {final_data}\n\n"
                    return

                step_count += 1

                # Skip empty middleware steps (e.g. {"HumanInTheLoopMiddleware.after_model": null})
                if all(v is None for v in step.values()):
                    continue

                # Send clean SSE events in AgentResult format
                for event in step_to_results(step, session_id):
                    event_data = json.dumps(event, ensure_ascii=False)
                    yield f"data: {event_data}\n\n"

            print(f"[SSE] Completed: {step_count} steps")

            # Final event: AgentResult format
            final_result = AgentResult(session_id=session_id)
            final_data = json.dumps(
                final_result.to_dict(),
                ensure_ascii=False,
                default=str
            )
            yield f"data: {final_data}\n\n"

        except Exception as e:
            print(f"[SSE ERROR] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False, default=str)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
