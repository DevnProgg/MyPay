from typing import Dict, Type
from app.providers.base import PaymentProvider
from app.providers.cpay_provider import CPayProvider
from app.providers.mpesa_provider import MPesaProvider
from flask import current_app

# Provider registry
PROVIDERS: Dict[str, Type[PaymentProvider]] = {
    'cpay':  CPayProvider,
    'mpesa': MPesaProvider,
}


def get_provider(provider_name: str) -> PaymentProvider:
    """
    Get provider instance by name.

    Args:
        provider_name: Name of the provider ('cpay', 'mpesa', etc.)

    Returns:
        Initialized provider instance

    Raises:
        ValueError: If provider not found
    """
    provider_class = PROVIDERS.get(provider_name.lower())

    if not provider_class:
        raise ValueError(f'Unknown provider: {provider_name}')

    config = _get_provider_config(provider_name.lower())
    return provider_class(config)


def _get_provider_config(provider_name: str) -> dict:
    """Get provider configuration from Flask app config."""

    if provider_name == 'mpesa':
        return {
            # Required
            'consumer_key':    current_app.config.get('MPESA_CONSUMER_KEY'),
            'consumer_secret': current_app.config.get('MPESA_CONSUMER_SECRET'),
            'shortcode':       current_app.config.get('MPESA_SHORTCODE'),
            'passkey':         current_app.config.get('MPESA_PASSKEY'),
            # Environment
            'environment':       current_app.config.get('MPESA_ENV', 'sandbox'),
            # Callback / result URLs
            'callback_url':      current_app.config.get('MPESA_CALLBACK_URL', ''),
            'result_url':        current_app.config.get('MPESA_RESULT_URL', ''),
            'queue_timeout_url': current_app.config.get('MPESA_QUEUE_TIMEOUT_URL', ''),
            # Optional – needed for B2C / reversal / status queries
            'initiator_name':      current_app.config.get('MPESA_INITIATOR_NAME', ''),
            'security_credential': current_app.config.get('MPESA_SECURITY_CREDENTIAL', ''),
            # Payment behaviour
            'transaction_type': current_app.config.get('MPESA_TRANSACTION_TYPE', 'CustomerPayBillOnline'),
            'identifier_type':  current_app.config.get('MPESA_IDENTIFIER_TYPE', '4'),
        }

    elif provider_name == 'cpay':
        return {
            # Required
            'api_key':      current_app.config.get('CPAY_API_KEY'),
            'api_secret':   current_app.config.get('CPAY_API_SECRET'),
            'client_code':  current_app.config.get('CPAY_CLIENT_CODE'),
            # Optional / environment-specific
            'base_url':     current_app.config.get(
                                'CPAY_BASE_URL',
                                'https://cpay-uat-env.chaperone.co.ls:5100'
                            ),
            'redirect_url': current_app.config.get('CPAY_REDIRECT_URL', ''),
            # Set to False only when running against UAT with a self-signed cert
            'verify_ssl':   current_app.config.get('CPAY_VERIFY_SSL', True),
        }

    return {}


def list_available_providers():
    """List all available providers."""
    return list(PROVIDERS.keys())


__all__ = ['get_provider', 'list_available_providers', 'PROVIDERS']