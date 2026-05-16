from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import BudgetMonth, Category, Transaction, User
from app.schemas.budget import (
    BudgetAssignRequest,
    BudgetCategoryRow,
    BudgetMonthView,
)

router = APIRouter(prefix="/budget", tags=["budget"])


@router.post("/assign", status_code=status.HTTP_204_NO_CONTENT)
async def assign_to_category(
    body: BudgetAssignRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    category = await session.get(Category, body.category_id)
    if category is None or category.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    stmt = (
        pg_insert(BudgetMonth)
        .values(
            user_id=user.id,
            category_id=body.category_id,
            year=body.year,
            month=body.month,
            assigned_amount=body.assigned_amount,
        )
        .on_conflict_do_update(
            constraint="uq_budget_user_period_cat",
            set_={"assigned_amount": body.assigned_amount},
        )
    )
    await session.execute(stmt)
    await session.commit()


@router.get("/{year}/{month}", response_model=BudgetMonthView)
async def get_month_view(
    year: int = Path(ge=1900, le=3000),
    month: int = Path(ge=1, le=12),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BudgetMonthView:
    categories = (
        await session.scalars(
            select(Category)
            .where(Category.user_id == user.id, Category.archived.is_(False))
            .order_by(Category.group_name.nulls_last(), Category.name)
        )
    ).all()

    # This month's activity per category (Plaid amounts: positive = outflow)
    activity_rows = (
        await session.execute(
            select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.user_id == user.id,
                Transaction.category_id.is_not(None),
                func.extract("year", Transaction.date) == year,
                func.extract("month", Transaction.date) == month,
            )
            .group_by(Transaction.category_id)
        )
    ).all()
    activity_by_cat: dict = {cat_id: Decimal(str(amount)) for cat_id, amount in activity_rows}

    # This month's assigned per category
    assigned_rows = (
        await session.execute(
            select(BudgetMonth.category_id, BudgetMonth.assigned_amount).where(
                BudgetMonth.user_id == user.id,
                BudgetMonth.year == year,
                BudgetMonth.month == month,
            )
        )
    ).all()
    assigned_by_cat: dict = {cat_id: amount for cat_id, amount in assigned_rows}

    # Cumulative available per category = sum(assigned) up to & incl this month
    #   minus sum(activity) up to & incl this month.
    period_cutoff = year * 100 + month

    cum_assigned_rows = (
        await session.execute(
            select(BudgetMonth.category_id, func.coalesce(func.sum(BudgetMonth.assigned_amount), 0))
            .where(
                BudgetMonth.user_id == user.id,
                (BudgetMonth.year * 100 + BudgetMonth.month) <= period_cutoff,
            )
            .group_by(BudgetMonth.category_id)
        )
    ).all()
    cum_assigned: dict = {cat_id: Decimal(str(amt)) for cat_id, amt in cum_assigned_rows}

    cum_activity_rows = (
        await session.execute(
            select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.user_id == user.id,
                Transaction.category_id.is_not(None),
                (
                    func.extract("year", Transaction.date) * 100
                    + func.extract("month", Transaction.date)
                )
                <= period_cutoff,
            )
            .group_by(Transaction.category_id)
        )
    ).all()
    cum_activity: dict = {cat_id: Decimal(str(amt)) for cat_id, amt in cum_activity_rows}

    rows: list[BudgetCategoryRow] = []
    total_assigned = Decimal("0")
    total_activity = Decimal("0")
    for cat in categories:
        assigned = Decimal(str(assigned_by_cat.get(cat.id, 0)))
        activity = activity_by_cat.get(cat.id, Decimal("0"))
        available = cum_assigned.get(cat.id, Decimal("0")) - cum_activity.get(cat.id, Decimal("0"))
        total_assigned += assigned
        total_activity += activity
        rows.append(
            BudgetCategoryRow(
                category_id=cat.id,
                name=cat.name,
                group_name=cat.group_name,
                assigned=assigned,
                activity=activity,
                available=available,
            )
        )

    return BudgetMonthView(
        year=year,
        month=month,
        categories=rows,
        total_assigned=total_assigned,
        total_activity=total_activity,
    )
