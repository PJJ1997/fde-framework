"""Chat router."""
import json
import uuid
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from llm import create_llm
from tools.registry import registry
from agents import create_agent, AgentInput, AgentResult
from context import context_manager

router = APIRouter(prefix="/api", tags=["chat"])


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

    # Save user message first (before agent processing)
    if text:
        context_manager.save_user_message(session_id, text)

    # Invoke agent - agent is responsible for building its own context
    result = await agent.invoke(AgentInput(
        session_id=session_id,
        user_input=text,
    ))

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

    # Save user message first (before agent processing)
    if text:
        context_manager.save_user_message(session_id, text)

    async def generate():
        """Generate SSE events from agent stream.

        All events are now AgentResult objects - no LangChain message processing needed.
        """
        try:
            step_count = 0
            has_confirmation = False

            async for result in agent.stream(AgentInput(
                session_id=session_id,
                user_input=text,
            )):
                # Agent.stream() now yields AgentResult objects
                step_count += 1

                # Check if this is a confirmation request (execution interrupted)
                if result.confirmation is not None:
                    has_confirmation = True

                # Send AgentResult as SSE event
                event_data = json.dumps(
                    result.to_dict(),
                    ensure_ascii=False,
                    default=str
                )
                yield f"data: {event_data}\n\n"

                # If confirmation required, stop streaming
                if has_confirmation:
                    print(f"[SSE] Interrupted for confirmation after {step_count} steps")
                    return

            print(f"[SSE] Completed: {step_count} steps")

            # Send final empty event to signal completion (if no confirmation)
            if not has_confirmation:
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
