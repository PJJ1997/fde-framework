"""ERP order tools with SQLite database."""
from typing import Dict, Any, Optional

from langchain_core.tools import StructuredTool

from .schemas import (
    CreateOrderInput,
    UpdateOrderInput,
    DeleteOrderInput,
    CancelOrderInput,
    ListOrderInput,
    GetOrderInput,
)
from .database import get_db


def create_order(
    customer_name: str,
    product_name: str,
    quantity: int,
    price: float,
    address: str,
) -> Dict[str, Any]:
    """创建新订单"""
    db = get_db()
    order = db.create_order(customer_name, product_name, quantity, price, address)
    return {"success": True, "order": order, "message": f"订单 {order['order_id']} 创建成功"}


def update_order(
    order_id: str,
    quantity: Optional[int] = None,
    price: Optional[float] = None,
    address: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """更新订单信息"""
    db = get_db()
    order = db.update_order(order_id, quantity, price, address, status)

    if not order:
        return {"success": False, "error": f"订单 {order_id} 不存在"}

    return {"success": True, "order": order, "message": f"订单 {order_id} 更新成功"}


def delete_order(order_id: str) -> Dict[str, Any]:
    """删除订单"""
    db = get_db()
    deleted_order = db.delete_order(order_id)

    if not deleted_order:
        return {"success": False, "error": f"订单 {order_id} 不存在"}

    return {"success": True, "order": deleted_order, "message": f"订单 {order_id} 已删除"}


def cancel_order(order_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """取消订单"""
    db = get_db()
    order = db.cancel_order(order_id, reason)

    if not order:
        # Check if order exists
        existing_order = db.get_order(order_id)
        if not existing_order:
            return {"success": False, "error": f"订单 {order_id} 不存在"}
        else:
            return {
                "success": False,
                "error": f"订单 {order_id} 当前状态为 {existing_order['status']}，无法取消",
            }

    return {"success": True, "order": order, "message": f"订单 {order_id} 已取消"}


def list_order(
    customer_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """查询订单列表"""
    db = get_db()
    orders = db.list_orders(customer_name, status, limit)

    return {
        "success": True,
        "orders": orders,
        "total": len(orders),
        "message": f"查询到 {len(orders)} 个订单",
    }


def get_order(order_id: str) -> Dict[str, Any]:
    """查询单个订单详情"""
    db = get_db()
    order = db.get_order(order_id)

    if not order:
        return {"success": False, "error": f"订单 {order_id} 不存在"}

    return {
        "success": True,
        "order": order,
        "message": f"查询到订单 {order_id}",
    }


# Create LangChain StructuredTools
create_order_tool = StructuredTool.from_function(
    func=create_order,
    name="create_order",
    description="创建新订单：根据客户信息、产品和地址创建一个新的订单。注意：本工具仅用于创建新订单，不能用于复制、恢复或重建已删除的订单。",
    args_schema=CreateOrderInput,
)

update_order_tool = StructuredTool.from_function(
    func=update_order,
    name="update_order",
    description="更新订单信息：修改订单的数量、价格、地址。注意：本工具用于修改订单内容，不是取消或删除订单。如需取消请用 cancel_order，如需彻底删除请用 delete_order。",
    args_schema=UpdateOrderInput,
)

delete_order_tool = StructuredTool.from_function(
    func=delete_order,
    name="delete_order",
    description="删除订单：从系统中彻底删除一个订单（物理删除，不可恢复）。注意：本工具是永久删除，不是取消订单。如需取消订单（保留记录、将状态改为已取消）请使用 cancel_order 工具。",
    args_schema=DeleteOrderInput,
)

cancel_order_tool = StructuredTool.from_function(
    func=cancel_order,
    name="cancel_order",
    description="取消订单：将订单状态改为已取消，保留订单记录并记录取消原因。注意：本工具是状态变更，订单记录仍然保留，不是物理删除。如需彻底删除订单请使用 delete_order 工具。",
    args_schema=CancelOrderInput,
)

list_order_tool = StructuredTool.from_function(
    func=list_order,
    name="list_order",
    description="查询订单列表：根据客户名称或状态筛选，返回多个订单的概要信息。注意：本工具返回订单列表，如需查询单个订单的详细信息请使用 get_order。",
    args_schema=ListOrderInput,
)

get_order_tool = StructuredTool.from_function(
    func=get_order,
    name="get_order",
    description="查询订单详情：根据订单ID获取单个订单的完整信息。注意：本工具仅查询单个订单，如需按条件筛选多个订单请使用 list_order。",
    args_schema=GetOrderInput,
)


TOOLS = [
    create_order_tool,
    update_order_tool,
    delete_order_tool,
    cancel_order_tool,
    list_order_tool,
    get_order_tool,
]
