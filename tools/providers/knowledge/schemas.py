"""Pydantic schemas for knowledge tools."""
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field


class KnowledgeSearchInput(BaseModel):
    """知识库检索的输入参数"""
    query: str = Field(..., description="检索查询文本")
    session_id: Optional[str] = Field(
        default=None,
        description="当前会话ID。传入后会自动结合最近对话上下文重写查询，提高检索准确率",
    )
    filter: Optional[Dict[str, Union[str, int, float, bool, Dict, List]]] = Field(
        default=None,
        description=(
            "元数据过滤条件，用于缩小检索范围。"
            "支持的操作符：$eq(等于), $ne(不等于), $gt(大于), $gte(大于等于), $lt(小于), $lte(小于等于), $in(包含于)。"
            "组合条件用 $and(且), $or(或)。"
            "示例："
            '{"category": "knowledge"} — 按类别过滤；'
            '{"created_at": {"$gte": "2025-01-01"}} — 按时间范围过滤；'
            '{"$and": [{"category": "knowledge"}, {"doc_type": "markdown"}]} — 组合条件过滤；'
            '{"tags": {"$in": ["agent", "tool"]}} — 按标签过滤'
        ),
    )
