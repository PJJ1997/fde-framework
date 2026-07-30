"""Build and persist structured context once for each new user turn."""
import json
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from context.manager import ContextManager, context_manager
from context.structured import StructuredConversationContext
from ..schemas import PlannerState
from .utils import clean_json_response

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """你是会话上下文解析器，只负责把对话整理成结构化上下文。

规则:
- 不生成执行计划，不选择或调用工具。
- 保留 previous_context 中仍然有效的实体、约束和事实。
- 当前用户明确提供的新值可以更新之前从对话推断的值。
- tool_facts 是成功工具调用产生的可信事实，不得猜测、删除或改写。
- 不得编造用户未提供、历史未出现、工具未返回的值。
- 无法唯一解析的指代放入 ambiguities；确实缺失的信息放入 missing_fields。
- current_request.raw_text 必须保留当前用户输入原文。
- summary 必须简短、客观。
- 输出必须符合指定的结构化 Schema。
"""


class ContextBuilderNode:
    """Create one complete structured context snapshot for a user turn."""

    def __init__(
        self,
        llm: BaseChatModel,
        manager: ContextManager = context_manager,
        max_messages: int = 10,
    ):
        self.llm = llm
        self.manager = manager
        self.max_messages = max_messages

    @staticmethod
    def _plain_content(stored_content: str) -> str:
        """Extract readable content from a persisted LangChain message."""
        try:
            data = json.loads(stored_content)
            if isinstance(data, dict):
                return str(data.get("content", ""))
        except (json.JSONDecodeError, TypeError):
            pass
        return stored_content

    def _build_payload(
        self,
        session_id: str,
        user_goal: str,
    ) -> tuple[dict, Optional[int]]:
        previous = (
            self.manager.get_structured_context(session_id)
            or StructuredConversationContext.empty()
        )
        history = self.manager.get_session_history(session_id)
        recent = history[-self.max_messages:]
        last_message_id = recent[-1].id if recent else None

        return {
            "previous_context": previous.model_dump(mode="json"),
            "current_user_input": user_goal,
            "recent_messages": [
                {
                    "message_id": message.id,
                    "role": message.role,
                    "content": self._plain_content(message.content),
                }
                for message in recent
            ],
        }, last_message_id

    def _invoke(self, messages: list) -> StructuredConversationContext:
        """Use native structured output, with validated JSON fallback."""
        try:
            structured_llm = self.llm.with_structured_output(
                StructuredConversationContext
            )
            result = structured_llm.invoke(messages)
            return StructuredConversationContext.model_validate(result)
        except Exception as structured_error:
            logger.warning(
                "Structured context output unavailable, using JSON fallback: %s",
                structured_error,
            )
            response = self.llm.invoke(messages)
            cleaned = clean_json_response(str(response.content))
            return StructuredConversationContext.model_validate_json(cleaned)

    def __call__(self, state: PlannerState) -> dict:
        """Build, validate, and persist context for the current user goal."""
        session_id = state.get("session_id", "")
        user_goal = state.get("user_goal", "")
        payload, last_message_id = self._build_payload(
            session_id,
            user_goal,
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=json.dumps(payload, ensure_ascii=False)
            ),
        ]
        context = self._invoke(messages)
        self.manager.save_structured_context(
            session_id,
            context,
            last_message_id=last_message_id,
        )
        return {"structured_context": context}
