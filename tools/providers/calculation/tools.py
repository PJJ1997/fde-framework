"""Calculation tools."""
from typing import Dict, Any
from langchain_core.tools import StructuredTool

from .schemas import AddInput, SubtractInput, MultiplyInput, DivideInput


def add(a: float, b: float) -> Dict[str, Any]:
    """加法运算"""
    return {"operation": "add", "a": a, "b": b, "result": a + b}


def subtract(a: float, b: float) -> Dict[str, Any]:
    """减法运算"""
    return {"operation": "subtract", "a": a, "b": b, "result": a - b}


def multiply(a: float, b: float) -> Dict[str, Any]:
    """乘法运算"""
    return {"operation": "multiply", "a": a, "b": b, "result": a * b}


def divide(a: float, b: float) -> Dict[str, Any]:
    """除法运算"""
    if b == 0:
        return {"operation": "divide", "a": a, "b": b, "error": "Division by zero"}
    return {"operation": "divide", "a": a, "b": b, "result": a / b}


# Create LangChain StructuredTools
add_tool = StructuredTool.from_function(
    func=add,
    name="add",
    description="加法运算:计算两个数字的和",
    args_schema=AddInput,
)

subtract_tool = StructuredTool.from_function(
    func=subtract,
    name="subtract",
    description="减法运算:计算两个数字的差",
    args_schema=SubtractInput,
)

multiply_tool = StructuredTool.from_function(
    func=multiply,
    name="multiply",
    description="乘法运算:计算两个数字的乘积",
    args_schema=MultiplyInput,
)

divide_tool = StructuredTool.from_function(
    func=divide,
    name="divide",
    description="除法运算:计算两个数字的商",
    args_schema=DivideInput,
)


TOOLS = [add_tool, subtract_tool, multiply_tool, divide_tool]