from typing import Dict, Type

from app.models import Account, ProviderConfig, ProviderTable
from app.providers.base import PaymentProvider
from app.providers.standard_bank_pay_provider import StandardBankPayProvider

# Provider registry
PROVIDERS: Dict[str, Type[PaymentProvider]] = {
    "StandardBankPay" : StandardBankPayProvider
}


def get_provider(provider_name: str, api_key : str) -> PaymentProvider:
    """
    Get provider instance by name.

    Args:
        provider_name: Name of the provider ('cpay', etc.)
        api_key: Api key to use for authentication

    Returns:
        Initialized provider instance

    Raises:
        ValueError: If provider not found
    """
    provider_class = PROVIDERS.get(provider_name.lower())

    if not provider_class:
        raise ValueError(f'Unknown provider: {provider_name}')

    config = _get_merchant_provider_config(provider_name.lower(), api_key)
    return provider_class(config)


def _get_merchant_provider_config(provider_name: str, merchant_api_key: str) -> dict | None:
    merchant_id = Account.query.filter_by(_api_key = merchant_api_key).first().to_dict()['merchant_id']
    provider_id = ProviderTable.query.filter_by(name = provider_name).first().to_dict()['id']
    if not merchant_id and not provider_id:
        return None
    else:
        config = ProviderConfig.query.filter_by(merchant_id = merchant_id, provider_id = provider_id).get("config")
        if not config:
            return None
        else:
            return config

def list_available_providers():
    """List all available providers."""
    return list(PROVIDERS)


__all__ = ['get_provider', 'list_available_providers', 'PROVIDERS']