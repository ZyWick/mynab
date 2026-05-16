from uuid import UUID

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    archived: bool | None = None


class CategoryOut(BaseModel):
    id: UUID
    name: str
    group_name: str | None
    archived: bool

    model_config = {"from_attributes": True}
