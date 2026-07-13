"""Knowledge search tool using RAG."""
from typing import Any, Dict, List, Optional, Union
from langchain_core.tools import StructuredTool

from .schemas import KnowledgeSearchInput
from llm import create_llm
from rag import RAGManager
from .rewriter import QueryRewriter

# Lazy singletons — created on first use
_manager: Optional[RAGManager] = None
_rewriter: Optional[QueryRewriter] = None


def _get_manager() -> RAGManager:
    global _manager
    if _manager is None:
        _manager = RAGManager()
    return _manager


def _get_rewriter() -> QueryRewriter:
    global _rewriter
    if _rewriter is None:
        llm = create_llm()
        _rewriter = QueryRewriter(llm=llm)
    return _rewriter


def knowledge_search(
    query: str,
    session_id: Optional[str] = None,
    filter: Optional[Dict[str, Union[str, int, float, bool, Dict, List]]] = None,
) -> Dict[str, Any]:
    """Search the knowledge base for relevant information.

    Uses vector similarity search to find the most relevant
    document chunks matching the query, optionally filtered by metadata.
    When session_id is provided, the query is rewritten using LLM
    with conversation context for better retrieval accuracy.
    """
    manager = _get_manager()
    try:
        # Rewrite query if session_id is provided
        search_query = query
        if session_id:
            rewriter = _get_rewriter()
            search_query = rewriter.rewrite(query, session_id=session_id)

        results = manager.search(search_query, filter=filter)
        if not results:
            return {"found": False, "message": "未找到相关信息"}

        contents = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "未知来源")
            contents.append(f"[{i}] (来源: {source})\n{doc.page_content}")

        return {
            "found": True,
            "count": len(results),
            "results": contents,
        }
    except Exception as e:
        return {"found": False, "error": str(e)}


knowledge_search_tool = StructuredTool.from_function(
    func=knowledge_search,
    name="knowledge_search",
    description=(
        "知识库检索：从知识库中检索与用户问题相关的信息。"
        "当用户的问题涉及专业知识、文档内容或特定领域信息时使用此工具。"
        "不是通用搜索工具，只能检索已导入知识库的内容。"
        "传入session_id后，会结合对话上下文自动重写查询，提高检索准确率。"
        "可通过filter参数按类别、标签、时间等元数据缩小检索范围。"
    ),
    args_schema=KnowledgeSearchInput,
)
