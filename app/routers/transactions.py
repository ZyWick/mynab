from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import Category, Transaction, User
from app.schemas.transaction import TransactionCategorize

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.patch("/{transaction_id}/category", status_code=status.HTTP_204_NO_CONTENT)
async def set_transaction_category(
    transaction_id: UUID,
    body: TransactionCategorize,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    tx = await session.get(Transaction, transaction_id)
    if tx is None or tx.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if body.category_id is not None:
        cat = await session.get(Category, body.category_id)
        if cat is None or cat.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    tx.category_id = body.category_id
    await session.commit()
