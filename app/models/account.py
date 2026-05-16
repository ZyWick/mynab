from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plaid_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("plaid_items.id", ondelete="CASCADE"), nullable=True
    )
    plaid_account_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    official_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mask: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    available_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
