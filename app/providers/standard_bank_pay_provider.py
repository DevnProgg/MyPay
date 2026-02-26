import requests
from typing import Dict, Any, Optional

from app.providers.base import (
    PaymentProvider,
    PaymentInitializationError,
    PaymentVerificationError,
    WebhookVerificationError,
)


class StandardBankPayProvider(PaymentProvider):
    """
    Adapter for Standard Bank Pay
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.base_url = config["base_url"]
        self.api_key = config["api_key"]
        self.client_id = config["client_id"]
        self.timeout = config.get("timeout", 30)

    # Internal helpers

    def _headers(self, request_id: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-SBP-Client-Id": self.client_id,
            "X-SBP-Request-Id": request_id,
            "Content-Type": "application/json",
        }

    def _map_status(self, sbp_status: str) -> str:
        """Normalize provider status to internal status"""
        mapping = {
            "AWAITING_CUSTOMER": "pending",
            "SETTLED": "completed",
        }
        return mapping.get(sbp_status, "processing")

    # Required interface

    def initialize_payment(
        self,
        amount: float,
        currency: str,
        customer_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        request_id = metadata.get("request_id") if metadata else None
        if not request_id:
            raise PaymentInitializationError("Missing request_id in metadata")

        payload = {
            "amount_cents": int(amount * 100),
            "currency": currency,
            "customer": customer_data,
            "callback_url": metadata.get("callback_url"),
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/payments/initiate",
                json=payload,
                headers=self._headers(request_id),
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise PaymentInitializationError(f"Network error: {e}") from e

        if resp.status_code >= 400:
            raise PaymentInitializationError(resp.text)

        data = resp.json()

        return {
            "transaction_id": data["sbp_txn_ref"],
            "status": self._map_status(data["processing_state"]),
            "payment_url": data.get("approval_url"),
            "additional_data": {
                "expires_in": data.get("expires_in_seconds"),
                "risk_score": data.get("meta", {}).get("risk_score"),
                "raw": data,
            },
        }


    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:

        request_id = f"verify-{provider_transaction_id}"

        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/payments/{provider_transaction_id}/status",
                headers=self._headers(request_id),
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise PaymentVerificationError(f"Network error: {e}") from e

        if resp.status_code >= 400:
            raise PaymentVerificationError(resp.text)

        data = resp.json()

        return {
            "status": self._map_status(data["processing_state"]),
            "amount": None,
            "currency": None,
            "additional_data": {
                "ledger_entry_id": data.get("ledger_entry_id"),
                "raw": data,
            },
        }


    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
         gateway has no signature.
        """
        if signature is None:
            return True
        return True


    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:

        event_type = payload.get("event_type")
        txn_ref = payload.get("sbp_txn_ref")

        if not txn_ref:
            raise WebhookVerificationError("Missing transaction reference")

        # Map webhook events
        status_map = {
            "PAYMENT_SETTLED": "completed",
        }

        normalized_status = status_map.get(event_type, "processing")

        return {
            "transaction_id": txn_ref,
            "event_type": event_type,
            "status": normalized_status,
            "additional_data": {
                "ledger_entry_id": payload.get("details", {}).get("ledger_entry_id"),
                "net_amount": payload.get("details", {}).get("net_amount"),
                "raw": payload,
            },
        }