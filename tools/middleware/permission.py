"""Permission middleware - enforces access control on tool calls.

Checks that the current user has the required permission before allowing
a tool to execute. Permissions follow the format: [system].[resource].[action]

Example: erp.order.write means write access to the order resource in the
ERP system.

Permissions are passed via the executor's context dict, typically
populated from the request body by the router layer.

Tools declare their required permission via the ``permission`` metadata
key, set during registration:
    registry.register(create_order_tool, permission="erp.order.write")
"""
from typing import Any, Dict, Optional

from langchain_core.tools import StructuredTool

from .base import ToolMiddleware


# Mapping from permission enum → user-friendly description.
# Add new entries here when adding new permission domains.
_PERMISSION_LABELS: Dict[str, str] = {
    "erp.order.read": "订单读取",
    "erp.order.write": "订单写入",
}


class PermissionDeniedError(Exception):
    """Raised when the user lacks the required permission for a tool."""

    def __init__(self, tool_name: str, required: str, user_permissions: list):
        self.tool_name = tool_name
        self.required = required
        self.user_permissions = user_permissions
        # Log detailed info server-side only
        print(
            f"[PermissionMiddleware] 权限不足: tool={tool_name}, "
            f"required={required}, user_permissions={user_permissions}"
        )
        # User-facing: specific permission label without internal names
        label = _PERMISSION_LABELS.get(required, "该操作")
        super().__init__(f"权限不足，缺少「{label}」权限")


class PermissionMiddleware(ToolMiddleware):
    """Check user permissions before tool execution.

    Reads the required permission from ``tool.metadata["permission"]``
    and the user's permissions from ``context["permissions"]``. If the
    required permission is not in the user's list, raises
    PermissionDeniedError.

    If a tool has no ``permission`` metadata, it is allowed by default
    (backward compatible).
    """

    async def before_execute(
        self,
        tool: StructuredTool,
        args: dict,
        context: Optional[dict] = None,
    ) -> None:
        """Check permission before tool execution."""
        required = (tool.metadata or {}).get("permission")
        if not required:
            return  # No permission required — allow

        user_permissions = (context or {}).get("permissions", [])
        if required not in user_permissions:
            raise PermissionDeniedError(tool.name, required, user_permissions)
