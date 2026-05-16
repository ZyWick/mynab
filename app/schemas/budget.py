from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class BudgetAssignRequest(BaseModel):
    category_id: UUID
    year: int = Field(ge=1900, le=3000)
    month: int = Field(ge=1, le=12)
    assigned_amount: Decimal


class BudgetCategoryRow(BaseModel):
    category_id: UUID
    name: str
    group_name: str | None
    assigned: Decimal
    activity: Decimal
    available: Decimal


class BudgetMonthView(BaseModel):
    year: int
    month: int
    categories: list[BudgetCategoryRow]
    total_assigned: Decimal
    total_activity: Decimal
