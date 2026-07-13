"""Query rewriter — uses LLM to refine user queries for better retrieval.

Transforms colloquial user input into concise, search-friendly queries
enriched with context from recent conversation history.
"""
from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from context.manager import ContextManager

_REWRITE_SYSTEM_PROMPT = """你是一个查询改写助手。你的任务是将用户的口语化问题改写为更适合知识库检索的查询文本。

改写规则：
1. 保留用户问题的核心意图
2. 将口语化表达转为书面化、专业化的关键词
3. 补充上下文中隐含的背景信息（如指代消解："它"→具体名称）
4. 提取关键实体和概念，去除无意义的语气词
5. 输出仅包含改写后的查询文本，不要解释

示例：
- 用户："这个agent怎么用啊" → "LLM Agent 使用方法"
- 用户："react是什么意思" → "ReAct Agent 架构原理与实现"
- 用户："刚才说的那个工具怎么调用" →（结合上下文）"知识库检索工具调用方法"
- 用户："权限怎么搞" → "Agent 权限控制与中间件配置"
"""


class QueryRewriter:
    """Rewrite user queries using LLM + conversation history for better retrieval."""

    def __init__(
        self,
        llm: BaseChatModel,
        context_manager: Optional[ContextManager] = None,
        history_limit: int = 20,
    ):
        self._llm = llm
        self._context_manager = context_manager or ContextManager()
        self._history_limit = history_limit

    def rewrite(self, query: str, session_id: Optional[str] = None) -> str:
        """Rewrite a user query for better retrieval.

        Args:
            query: Original user query.
            session_id: If provided, load recent conversation history
                to enrich the rewritten query with context.

        Returns:
            Rewritten query string. Falls back to original query on failure.
        """
        try:
            messages: List[BaseMessage] = [SystemMessage(content=_REWRITE_SYSTEM_PROMPT)]

            # Add conversation history for context
            if session_id:
                history = self._context_manager.get_conversations(session_id)
                if history:
                    # Take last N messages
                    recent = history[-self._history_limit:]
                    history_text = "\n".join(
                        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
                        for m in recent
                        if m.get("content")
                    )
                    if history_text:
                        messages.append(HumanMessage(
                            content=f"以下是最近的对话上下文：\n{history_text}\n\n"
                            f"请改写以下查询：{query}"
                        ))
                    else:
                        messages.append(HumanMessage(content=f"请改写以下查询：{query}"))
                else:
                    messages.append(HumanMessage(content=f"请改写以下查询：{query}"))
            else:
                messages.append(HumanMessage(content=f"请改写以下查询：{query}"))

            response = self._llm.invoke(messages)
            rewritten = response.content.strip()

            # Safety: if rewrite is empty or too short, fall back
            if not rewritten or len(rewritten) < 2:
                return query

            return rewritten

        except Exception as e:
            print(f"[QueryRewriter] Rewrite failed, using original query: {e}")
            return query
