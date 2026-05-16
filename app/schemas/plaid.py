from pydantic import BaseModel


class LinkTokenResponse(BaseModel):
    link_token: str
    expiration: str


class ExchangePublicTokenRequest(BaseModel):
    public_token: str


class ExchangePublicTokenResponse(BaseModel):
    plaid_item_id: str
    institution_name: str | None = None
    accounts_added: int


class SyncResponse(BaseModel):
    items_synced: int
    transactions_added: int
    transactions_modified: int
    transactions_removed: int
