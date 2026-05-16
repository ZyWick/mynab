from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import Category, User
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryOut]:
    stmt = select(Category).where(Category.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Category.archived.is_(False))
    stmt = stmt.order_by(Category.group_name.nulls_last(), Category.name)
    rows = (await session.scalars(stmt)).all()
    return [CategoryOut.model_validate(r) for r in rows]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = Category(user_id=user.id, name=body.name, group_name=body.group_name)
    session.add(category)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category with this name already exists",
        ) from e
    await session.refresh(category)
    return CategoryOut.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: UUID,
    body: CategoryUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = await _get_owned_category(session, user, category_id)

    if body.name is not None:
        category.name = body.name
    if body.group_name is not None:
        category.group_name = body.group_name
    if body.archived is not None:
        category.archived = body.archived

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category with this name already exists",
        ) from e
    await session.refresh(category)
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    category = await _get_owned_category(session, user, category_id)
    await session.delete(category)
    await session.commit()


async def _get_owned_category(session: AsyncSession, user: User, category_id: UUID) -> Category:
    category = await session.get(Category, category_id)
    if category is None or category.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category
