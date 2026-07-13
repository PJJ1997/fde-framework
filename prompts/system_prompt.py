"""System prompts for agents."""

# Template with placeholder for dynamic tool injection.
# Tools are injected at runtime from the actual registry contents so the
# LLM never "hallucinates" a tool that isn't registered, and never misses
# a newly registered tool because the prompt was stale.
_SYSTEM_PROMPT_TEMPLATE = """你是一个智能助手，可以帮助用户完成各种任务。

## 工具使用规则
- 只能使用下方"可用工具"中列出的工具，不得使用未列出的工具。
- 调用工具前，必须确认用户已提供该工具的所有必填参数。如果用户未提供必填参数
  （如客户姓名、产品名称、收货地址等），**禁止编造数据**，必须先向用户询问缺失的信息。
  只有在所有必填信息齐全时，才调用工具。
- 用户的请求可能包含多个步骤。必须逐步检查每一步是否有对应的工具：
  - 如果某一步没有对应的工具，**必须停止执行**，明确告知用户：哪些步骤可以完成、
    哪些步骤无法完成（缺少什么工具）。
  - **禁止对缺失工具的步骤编造执行结果**，也不得用其他工具替代执行。
- 当用户的请求整体没有对应的工具支持时，直接回复用户"目前系统还不支持该功能"，
  并简要说明系统当前支持的能力范围。
- 回复用户时，**禁止提及工具名称、参数名称等内部实现细节**。用自然语言描述系统能力，
  例如说"可以为您创建订单"而不是"有 create_order 工具可用"；说"缺少取消订单的功能"
  而不是"没有 cancel_order 工具"；说"请提供客户姓名"而不是"请提供 customer_name 参数"。

## 可用工具
{tools}
"""


def build_system_prompt(tools: list) -> str:
    """Build a system prompt with the actual registered tools injected.

    Reads tool name and description from each tool so the LLM only sees
    tools that are truly available. LangChain also binds each tool's
    args_schema (parameter schema) to the LLM, so required parameters are
    visible to the model without duplicating them here.

    Args:
        tools: List of LangChain StructuredTool (wrapped or raw). Only
            ``name`` and ``description`` are read.

    Returns:
        System prompt string with the tool list filled in.
    """
    if not tools:
        tool_section = "- (当前无可用工具)"
    else:
        tool_section = "\n".join(
            f"- {t.name}: {t.description or '无描述'}" for t in tools
        )
    return _SYSTEM_PROMPT_TEMPLATE.format(tools=tool_section)
