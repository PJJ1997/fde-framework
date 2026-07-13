"""Pydantic schemas for calculation tools."""
from pydantic import BaseModel, Field


class AddInput(BaseModel):
    a: float = Field(..., description="第一个数字")
    b: float = Field(..., description="第二个数字")


class SubtractInput(BaseModel):
    a: float = Field(..., description="第一个数字")
    b: float = Field(..., description="第二个数字")


class MultiplyInput(BaseModel):
    a: float = Field(..., description="第一个数字")
    b: float = Field(..., description="第二个数字")


class DivideInput(BaseModel):
    a: float = Field(..., description="第一个数字")
    b: float = Field(..., description="第二个数字")