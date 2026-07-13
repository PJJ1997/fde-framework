"""Actions router for resuming interrupted agent execution."""
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from llm import create_llm
from tools.registry import registry
from agents import create_agent, get_resume_data, AgentResult
from app.routers.chat import step_to_results

router = APIRouter(prefix="/api", tags=["actions"])


@router.post("/actions/confirm")
async def confirm_action(request: Request):
    """Confirm and resume an interrupted agent execution.

    Body:
        thread_id: The thread_id from the confirmation response.
        session_id: The session_id for context management.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    thread_id = body.get("thread_id")
    session_id = body.get("session_id")
    if not thread_id:
        return {"error": "thread_id is required"}

    llm = create_llm()
    permissions = body.get("permissions", [])
    context = {"session_id": session_id, "permissions": permissions}
    tools = registry.get_tools(context=context)
    agent = create_agent(llm, tools)

    resume_data = get_resume_data()
    result = await agent.resume(thread_id, resume_data, session_id=session_id)

    return result.to_dict()


@router.post("/actions/confirm_sse")
async def confirm_action_sse(request: Request):
    """Confirm and resume with SSE streaming output.

    Streams step-by-step output after resuming, so the frontend can show
    each node/tool result as it completes. Mirrors /api/chat_sse.

    Body:
        thread_id: The thread_id from the confirmation response.
        session_id: The session_id for context management.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    thread_id = body.get("thread_id")
    session_id = body.get("session_id")
    if not thread_id:
        return {"error": "thread_id is required"}

    llm = create_llm()
    permissions = body.get("permissions", [])
    context = {"session_id": session_id, "permissions": permissions}
    tools = registry.get_tools(context=context)
    agent = create_agent(llm, tools)

    resume_data = get_resume_data()

    async def generate():
        """Generate SSE events from agent resume_stream."""
        try:
            async for step in agent.resume_stream(
                thread_id, resume_data, session_id=session_id
            ):
                # AgentResult means another interrupt (chained confirmation)
                if isinstance(step, AgentResult):
                    final_data = json.dumps(
                        step.to_dict(), ensure_ascii=False, default=str
                    )
                    yield f"data: {final_data}\n\n"
                    return

                # Skip empty middleware steps
                if all(v is None for v in step.values()):
                    continue

                # Send clean SSE events in AgentResult format
                for event in step_to_results(step, session_id):
                    event_data = json.dumps(event, ensure_ascii=False)
                    yield f"data: {event_data}\n\n"

            # Final event
            final_result = AgentResult(session_id=session_id)
            final_data = json.dumps(
                final_result.to_dict(), ensure_ascii=False, default=str
            )
            yield f"data: {final_data}\n\n"

        except Exception as e:
            print(f"[CONFIRM SSE ERROR] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            error_data = json.dumps(
                {"error": str(e)}, ensure_ascii=False, default=str
            )
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
