from .calculation.tools import TOOLS as CALCULATION_TOOLS
from .erp.tools import (
    create_order_tool,
    update_order_tool,
    delete_order_tool,
    cancel_order_tool,
    list_order_tool,
    get_order_tool,
)

# Register tools on import
from ..registry import registry

# Calculation tools
for tool in CALCULATION_TOOLS:
    registry.register(tool)

# ERP tools
registry.register(create_order_tool, confirm=True)
registry.register(update_order_tool)
registry.register(delete_order_tool)
# registry.register(cancel_order_tool, confirm=True, permission="erp.order.write")
registry.register(list_order_tool)
registry.register(get_order_tool)

# Knowledge tools
from .knowledge.tools import knowledge_search_tool
registry.register(knowledge_search_tool)
