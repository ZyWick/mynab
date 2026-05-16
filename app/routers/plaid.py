from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.crypto import decrypt, encrypt
from app.db import get_session
from app.deps import get_current_user
from app.models import Account, PlaidItem, Transaction, User
from app.plaid_client import get_plaid_client
from app.schemas.plaid import (
    ExchangePublicTokenRequest,
    ExchangePublicTokenResponse,
    LinkTokenResponse,
    SyncResponse,
)

router = APIRouter(prefix="/plaid", tags=["plaid"])


@router.post("/link-token", response_model=LinkTokenResponse)
async def create_link_token(user: User = Depends(get_current_user)) -> LinkTokenResponse:
    settings = get_settings()
    client = get_plaid_client()

    req = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=str(user.id)),
        client_name="my-ynab",
        products=[Products(p.strip()) for p in settings.plaid_products.split(",") if p.strip()],
        country_codes=[CountryCode(c.strip()) for c in settings.plaid_country_codes.split(",") if c.strip()],
        language="en",
    )
    resp = client.link_token_create(req)
    return LinkTokenResponse(link_token=resp["link_token"], expiration=str(resp["expiration"]))


@router.post("/exchange-public-token", response_model=ExchangePublicTokenResponse)
async def exchange_public_token(
    body: ExchangePublicTokenRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ExchangePublicTokenResponse:
    client = get_plaid_client()

    exchange = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=body.public_token)
    )
    access_token: str = exchange["access_token"]
    plaid_item_id: str = exchange["item_id"]

    item_info = client.item_get(ItemGetRequest(access_token=access_token))
    institution_id = item_info["item"].get("institution_id")
    institution_name: str | None = None
    if institution_id:
        inst = client.institutions_get_by_id(
            InstitutionsGetByIdRequest(
                institution_id=institution_id,
                country_codes=[CountryCode("US")],
            )
        )
        institution_name = inst["institution"]["name"]

    item = PlaidItem(
        user_id=user.id,
        plaid_item_id=plaid_item_id,
        access_token_encrypted=encrypt(access_token),
        institution_id=institution_id,
        institution_name=institution_name,
    )
    session.add(item)
    await session.flush()

    accounts_resp = client.accounts_get(AccountsGetRequest(access_token=access_token))
    accounts_added = 0
    for a in accounts_resp["accounts"]:
        balances = a.get("balances", {})
        session.add(
            Account(
                user_id=user.id,
                plaid_item_id=item.id,
                plaid_account_id=a["account_id"],
                name=a.get("name") or "",
                official_name=a.get("official_name"),
                type=str(a.get("type")) if a.get("type") is not None else None,
                subtype=str(a.get("subtype")) if a.get("subtype") is not None else None,
                mask=a.get("mask"),
                current_balance=_to_decimal(balances.get("current")),
                available_balance=_to_decimal(balances.get("available")),
                iso_currency_code=balances.get("iso_currency_code"),
            )
        )
        accounts_added += 1

    await session.commit()
    return ExchangePublicTokenResponse(
        plaid_item_id=plaid_item_id,
        institution_name=institution_name,
        accounts_added=accounts_added,
    )


@router.post("/sync", response_model=SyncResponse)
async def sync_transactions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SyncResponse:
    client = get_plaid_client()

    items = (await session.scalars(select(PlaidItem).where(PlaidItem.user_id == user.id))).all()
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No linked Plaid items")

    total_added = 0
    total_modified = 0
    total_removed = 0

    for item in items:
        access_token = decrypt(item.access_token_encrypted)
        cursor: str | None = item.transactions_cursor
        has_more = True

        account_map: dict[str, Account] = {
            a.plaid_account_id: a
            for a in (
                await session.scalars(
                    select(Account).where(Account.plaid_item_id == item.id)
                )
            ).all()
            if a.plaid_account_id
        }

        while has_more:
            req = TransactionsSyncRequest(access_token=access_token)
            if cursor:
                req.cursor = cursor
            resp = client.transactions_sync(req)

            for tx in resp["added"]:
                account = account_map.get(tx["account_id"])
                if account is None:
                    continue
                session.add(
                    Transaction(
                        user_id=user.id,
                        account_id=account.id,
                        plaid_transaction_id=tx["transaction_id"],
                        date=tx["date"],
                        amount=_to_decimal(tx["amount"]) or Decimal("0"),
                        iso_currency_code=tx.get("iso_currency_code"),
                        payee=tx.get("merchant_name") or tx.get("name"),
                        memo=tx.get("name"),
                        pending=bool(tx.get("pending", False)),
                        raw=_to_jsonable(tx),
                    )
                )
                total_added += 1

            for tx in resp["modified"]:
                existing = await session.scalar(
                    select(Transaction).where(Transaction.plaid_transaction_id == tx["transaction_id"])
                )
                if existing is None:
                    continue
                existing.date = tx["date"]
                existing.amount = _to_decimal(tx["amount"]) or Decimal("0")
                existing.iso_currency_code = tx.get("iso_currency_code")
                existing.payee = tx.get("merchant_name") or tx.get("name")
                existing.memo = tx.get("name")
                existing.pending = bool(tx.get("pending", False))
                existing.raw = _to_jsonable(tx)
                total_modified += 1

            for removed in resp["removed"]:
                existing = await session.scalar(
                    select(Transaction).where(
                        Transaction.plaid_transaction_id == removed["transaction_id"]
                    )
                )
                if existing is not None:
                    await session.delete(existing)
                    total_removed += 1

            cursor = resp["next_cursor"]
            has_more = bool(resp["has_more"])

        item.transactions_cursor = cursor

    await session.commit()
    return SyncResponse(
        items_synced=len(items),
        transactions_added=total_added,
        transactions_modified=total_modified,
        transactions_removed=total_removed,
    )


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _to_jsonable(obj):
    """Plaid SDK returns model objects; coerce to plain JSON-safe dicts."""
    if hasattr(obj, "to_dict"):
        return _to_jsonable(obj.to_dict())
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
