from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class PaymentProvider(ABC):
    """Abstract base class for payment providers"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration

        Args:
            config: Provider-specific configuration
        """
        self.config = config
        self.provider_name = self.__class__.__name__.replace('Provider', '').lower()

    @abstractmethod
    def initialize_payment(
            self,
            amount: float,
            currency: str,
            customer_data: Dict[str, Any],
            metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a payment transaction

        Args:
            amount: Payment amount
            currency: Currency code (e.g., 'ZAR', 'USD')
            customer_data: Customer information
            metadata: Additional metadata

        Returns:
            Dict containing:
                - transaction_id: Provider's transaction ID
                - status: Payment status
                - payment_url: URL for customer to complete payment (if applicable)
                - additional_data: Any additional provider-specific data
        """
        pass

    @abstractmethod
    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:
        """
        Verify payment status with the provider

        Args:
            provider_transaction_id: Provider's transaction ID

        Returns:
            Dict containing:
                - status: Payment status
                - amount: Payment amount
                - currency: Currency code
                - additional_data: Provider-specific data
        """
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature

        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers

        Returns:
            True if signature is valid, False otherwise
        """
        pass

    @abstractmethod
    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process webhook event

        Args:
            payload: Webhook payload

        Returns:
            Dict containing:
                - transaction_id: Provider's transaction ID
                - event_type: Type of event
                - status: Updated payment status
                - additional_data: Event-specific data
        """
        pass

    def get_provider_name(self) -> str:
        """Get provider name"""
        return self.provider_name


class PaymentProviderError(Exception):
    """Base exception for provider errors"""
    pass


class PaymentInitializationError(PaymentProviderError):
    """Raised when payment initialization fails"""
    pass


class PaymentVerificationError(PaymentProviderError):
    """Raised when payment verification fails"""
    pass


class WebhookVerificationError(PaymentProviderError):
    """Raised when webhook verification fails"""
    pass