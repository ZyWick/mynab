from functools import lru_cache

from plaid import Configuration, Environment, ApiClient
from plaid.api import plaid_api

from app.config import get_settings


_ENV_MAP = {
    "sandbox": Environment.Sandbox,
    "production": Environment.Production,
}


@lru_cache
def get_plaid_client() -> plaid_api.PlaidApi:
    settings = get_settings()
    host = _ENV_MAP.get(settings.plaid_env.lower(), Environment.Sandbox)
    config = Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(ApiClient(config))
