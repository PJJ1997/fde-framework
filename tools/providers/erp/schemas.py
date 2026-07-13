"""Pydantic schemas for ERP order tools."""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class CreateOrderInput(BaseModel):
    """创建订单的输入参数"""
    customer_name: str = Field(..., description="客户姓名")
    product_name: str = Field(..., description="产品名称")
    quantity: int = Field(..., description="数量")
    price: float = Field(..., description="单价")
    address: str = Field(..., description="收货地址")


class UpdateOrderInput(BaseModel):
    """更新订单的输入参数"""
    order_id: str = Field(..., description="订单ID")
    quantity: Optional[int] = Field(None, description="数量")
    price: Optional[float] = Field(None, description="单价")
    address: Optional[str] = Field(None, description="收货地址")
    status: Optional[str] = Field(None, description="订单状态")


class DeleteOrderInput(BaseModel):
    """删除订单的输入参数"""
    order_id: str = Field(..., description="订单ID")


class CancelOrderInput(BaseModel):
    """取消订单的输入参数"""
    order_id: str = Field(..., description="订单ID")
    reason: Optional[str] = Field(None, description="取消原因")


class ListOrderInput(BaseModel):
    """查询订单列表的输入参数"""
    customer_name: Optional[str] = Field(None, description="客户姓名（可选筛选条件）")
    status: Optional[str] = Field(None, description="订单状态（可选筛选条件）")
    limit: Optional[int] = Field(10, description="返回数量限制，默认10")


class GetOrderInput(BaseModel):
    """查询单个订单的输入参数"""
    order_id: str = Field(..., description="订单ID")