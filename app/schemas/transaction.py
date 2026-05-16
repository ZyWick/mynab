from uuid import UUID

from pydantic import BaseModel


class TransactionCategorize(BaseModel):
    category_id: UUID | None
