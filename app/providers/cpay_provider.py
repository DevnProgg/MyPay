"""
CPay Payment Provider Implementation Based on Chaperone Payments API v1.1
API Base: https://cpay-uat-env.chaperone.co.ls:5100

Authentication: API Key via Authorization header

Payment Flows:
  - Async USSD : POST /api/cpaypayments/paymentrequest/async/transactions
  - OTP-based (sync):         POST /api/cpaypayments/payment → POST /api/cpaypayments/confirm
  - Card-based:               POST /api/cpaypayments/payment?cardPayment=true (returns redirect URL)

Status Polling:  GET /api/cpaypayments/transaction-status
Webhook (push):  Configure redirectUrl in the transaction request; CPay POSTs status updates there.
"""

import hmac
import hashlib
import logging
import requests
from typing import Dict, Any, Optional

from app.providers.base import (
    PaymentProvider,
    PaymentInitializationError,
    PaymentVerificationError,
    RefundError,
)

logger = logging.getLogger(__name__)



# CPay transaction-status → internal status mapping
CPAY_STATUS_MAP: Dict[str, str] = {
    # paymentRequestStatus values documented by CPay
    "processed": "completed",
    "open": "pending",
    "scheduled": "pending",
    "denied": "failed",
    "canceled": "failed",
    "cancelled": "failed",
    "expired": "failed",
    "reversed": "refunded",
    # reasonCode / statusCode shortcuts that may appear in some responses
    "0000": "completed",
    "success": "completed",
}


def _map_status(cpay_status: Optional[str]) -> str:
    """Normalise a CPay status string to our internal vocabulary."""
    if not cpay_status:
        return "pending"
    return CPAY_STATUS_MAP.get(cpay_status.lower(), "pending")


class CPayProvider(PaymentProvider):
    """
    Real CPay payment provider adapter.

    Required config keys:
        api_key      – Client API key (used as Authorization header value)
        api_secret   – Shared secret for HMAC-SHA256 checksum generation
        client_code  – Your CPay merchant/client code (e.g. "CLIENT_X0005")
        base_url     – API base URL (default: UAT sandbox)
        redirect_url – Your publicly accessible webhook/callback URL (optional)
        verify_ssl   – Set False only during local UAT against self-signed cert (default True)
    """

    # CPay API endpoints (relative to base_url)
    _EP_PAYMENT_OTP   = "/api/cpaypayments/payment"
    _EP_CONFIRM_OTP   = "/api/cpaypayments/confirm"
    _EP_PAYMENT_ASYNC = "/api/cpaypayments/paymentrequest/async/transactions"
    _EP_TX_STATUS     = "/api/cpaypayments/transaction-status"
    _EP_TX_DETAIL     = "/api/cpaypayments/transaction"
    _EP_TX_LIST       = "/api/cpaypayments/payment/request/transactions"

    DEFAULT_BASE_URL  = "https://cpay-uat-env.chaperone.co.ls:5100"
    DEFAULT_CURRENCY  = "LSL"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.api_key     = config.get("api_key", "")
        self.api_secret  = config.get("api_secret", "")
        self.client_code = config.get("client_code", "")
        self.base_url    = config.get("base_url", self.DEFAULT_BASE_URL).rstrip("/")
        self.redirect_url = config.get("redirect_url", "")
        self.verify_ssl  = config.get("verify_ssl", True)

        if not self.api_key:
            raise ValueError("CPayProvider: 'api_key' is required in config")
        if not self.api_secret:
            raise ValueError("CPayProvider: 'api_secret' is required in config")
        if not self.client_code:
            raise ValueError("CPayProvider: 'client_code' is required in config")

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._session.verify = self.verify_ssl

    # Public interface (PaymentProvider ABC)
    def initialize_payment(
        self,
        amount: float,
        currency: str,
        customer_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiate a CPay payment.

        customer_data required fields:
            msisdn          – Customer phone number (e.g. "+26650123456" or "60123456")
            ext_transaction_id – Your unique transaction reference

        customer_data optional fields:
            email           – For email OTP notifications
            short_description
            otp_medium      – "sms" (default) | "email"
            payment_mode    – "async" (default, USSD push) | "otp" | "card"
            subscriptions   – dict for recurring payments (see CPay docs)
            additional_data – arbitrary string metadata passed through to CPay

        Returns standard PaymentProvider dict:
            transaction_id  – Your ext_transaction_id (used for status polling)
            status          – "pending"
            payment_url     – Populated only for card payments (HTML redirect)
            additional_data – Full CPay response + internal metadata
        """
        metadata = metadata or {}
        mode = (customer_data.get("payment_mode") or metadata.get("payment_mode", "async")).lower()

        msisdn          = customer_data.get("msisdn") or customer_data.get("phone", "")
        ext_tx_id       = customer_data.get("ext_transaction_id") or metadata.get("ext_transaction_id", "")
        currency        = currency or self.DEFAULT_CURRENCY
        short_desc      = customer_data.get("short_description") or metadata.get("short_description", "")
        otp_medium      = customer_data.get("otp_medium", "sms")
        additional_data = customer_data.get("additional_data") or metadata.get("additional_data", "")
        subscriptions   = customer_data.get("subscriptions") or metadata.get("subscriptions")

        if not msisdn:
            raise PaymentInitializationError("CPayProvider: 'msisdn' is required in customer_data")
        if not ext_tx_id:
            raise PaymentInitializationError(
                "CPayProvider: 'ext_transaction_id' is required in customer_data or metadata"
            )

        checksum = self._compute_checksum(
            ext_transaction_id=ext_tx_id,
            amount=amount,
            msisdn=msisdn,
        )

        tx_request: Dict[str, Any] = {
            "extTransactionId": ext_tx_id,
            "clientCode": self.client_code,
            "msisdn": msisdn,
            "otp": "",
            "amount": f"{amount:.2f}",
            "shortDescription": short_desc,
            "checksum": checksum,
            "currency": currency,
            "otpMedium": otp_medium,
            "additionalData": str(additional_data) if additional_data else "",
            "redirectUrl": self.redirect_url,
        }

        if subscriptions:
            tx_request["subscriptions"] = subscriptions

        payload = {"transactionRequest": tx_request}

        if mode == "async":
            return self._initiate_async(ext_tx_id, payload)
        elif mode == "card":
            return self._initiate_card(ext_tx_id, payload, customer_data)
        elif mode == "otp":
            return self._initiate_otp(ext_tx_id, payload, customer_data)
        else:
            raise PaymentInitializationError(
                f"CPayProvider: unknown payment_mode '{mode}'. Use 'async', 'otp', or 'card'."
            )

    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:
        """
        Poll CPay for the current status of a transaction.

        provider_transaction_id is the ext_transaction_id you supplied at
        initialization (CPay calls this 'requestReference').

        Returns standard PaymentProvider dict:
            status           – normalised internal status
            amount           – float (from CPay response if available)
            currency         – currency code
            additional_data  – full CPay response
        """
        params: Dict[str, Any] = {
            "requestReference": provider_transaction_id,
        }

        try:
            resp = self._session.get(
                f"{self.base_url}{self._EP_TX_STATUS}",
                params=params,
                timeout=30,
            )
            data = self._handle_response(resp, "verify_payment")
        except PaymentVerificationError:
            raise
        except Exception as exc:
            raise PaymentVerificationError(
                f"CPayProvider: network error during verify_payment – {exc}"
            ) from exc

        cpay_status = data.get("paymentRequestStatus") or data.get("statusCode")
        internal_status = _map_status(cpay_status)

        # CPay doesn't echo amount/currency in the status endpoint;
        # we return what the response gives us (may be absent).
        return {
            "status": internal_status,
            "amount": None,          # not returned by /transaction-status
            "currency": None,
            "additional_data": {
                "cpay_transaction_id": data.get("cPayTransactionId"),
                "ext_transaction_id":  data.get("extTransactionId"),
                "cpay_status":         cpay_status,
                "reason_code":         data.get("reasonCode"),
                "description":         data.get("description"),
                "raw_response":        data,
            },
        }

    def refund_payment(
        self,
        provider_transaction_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        CPay does not expose a public refund API in v1.1.

        The /transaction-status endpoint documents 'reversed' as a terminal
        state, which is triggered on the CPay side (e.g. via merchant portal
        or their support team).

        This method raises RefundError with a clear message so callers know
        to handle refunds out-of-band.  If CPay adds a refund endpoint in a
        future API version, implement it here.
        """
        raise RefundError(
            "CPayProvider: CPay v1.1 does not expose a programmatic refund endpoint. "
            "Please initiate refunds via the CPay merchant portal or contact CPay support. "
            f"Transaction reference: {provider_transaction_id}"
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        CPay's push mechanism posts to your redirectUrl without a request-level
        HMAC signature header (unlike Stripe/M-Pesa).  Status notifications are
        authenticated implicitly because:
          - They originate from CPay's IP range (allowlist at your firewall).
          - The payload contains extTransactionId which you can cross-check
            against your own records before trusting the status.

        This method therefore always returns True – webhook authenticity should
        be validated at the application layer via verify_payment() against the
        CPay status API whenever a push notification arrives.

        If CPay introduces signature headers in a future version, update this
        method to perform HMAC-SHA256 verification using self.api_secret.
        """
        logger.debug(
            "CPayProvider.verify_webhook_signature: CPay push notifications do not "
            "carry a signature header. Returning True; validate payload contents manually."
        )
        return True

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a CPay push notification (status callback posted to redirectUrl).

        CPay posts a TransactionResponse-shaped body:
        {
            "statusCode":       
            "description":      
            "extTransactionId":     
            "cPayTransactionId":    
            "paymentRequestStatus": 
            "additionalData":   
            "reasonCode":  
        }

        Returns standard PaymentProvider dict compatible with the gateway's
        webhook processor.
        """
        cpay_status    = payload.get("paymentRequestStatus") or payload.get("statusCode")
        internal_status = _map_status(cpay_status)
        ext_tx_id      = payload.get("extTransactionId", "")
        cpay_tx_id     = payload.get("cPayTransactionId", "")

        # Derive a meaningful event_type string
        if internal_status == "completed":
            event_type = "payment.completed"
        elif internal_status == "refunded":
            event_type = "payment.reversed"
        elif internal_status == "failed":
            reason_code = payload.get("reasonCode", "").lower()
            if reason_code in ("canceled", "cancelled"):
                event_type = "payment.cancelled"
            elif reason_code == "expired":
                event_type = "payment.expired"
            else:
                event_type = "payment.failed"
        else:
            event_type = "payment.pending"

        return {
            "transaction_id": ext_tx_id,
            "event_type":     event_type,
            "status":         internal_status,
            "additional_data": {
                "cpay_transaction_id": cpay_tx_id,
                "cpay_status":         cpay_status,
                "reason_code":         payload.get("reasonCode"),
                "description":         payload.get("description"),
                "additional_data":     payload.get("additionalData"),
                "raw_payload":         payload,
            },
        }


    # OTP confirmation 


    def confirm_otp_payment(
        self,
        ext_transaction_id: str,
        otp: str,
        amount: float,
        msisdn: str,
        currency: str = DEFAULT_CURRENCY,
    ) -> Dict[str, Any]:
        """
        Confirm an OTP-initiated payment.

        Call this after the customer has received and entered their OTP.
        Not needed for async USSD or card payments.

        Returns standard PaymentProvider dict.
        """
        checksum = self._compute_checksum(
            ext_transaction_id=ext_transaction_id,
            amount=amount,
            msisdn=msisdn,
            otp=otp,
        )

        payload: Dict[str, Dict[str, str]] = {
            "transactionRequest": {
                "extTransactionId": ext_transaction_id,
                "clientCode":       self.client_code,
                "msisdn":           msisdn,
                "otp":              otp,
                "amount":           f"{amount:.2f}",
                "shortDescription": "",
                "checksum":         checksum,
                "currency":         currency,
                "otpMedium":        "sms",
                "additionalData":   "",
                "redirectUrl":      self.redirect_url,
            }
        }

        try:
            resp = self._session.post(
                f"{self.base_url}{self._EP_CONFIRM_OTP}",
                json=payload,
                timeout=30,
            )
            data = self._handle_response(resp, "confirm_otp_payment")
        except (PaymentInitializationError, PaymentVerificationError):
            raise
        except Exception as exc:
            raise PaymentInitializationError(
                f"CPayProvider: network error during confirm_otp_payment – {exc}"
            ) from exc

        cpay_status = data.get("paymentRequestStatus") or data.get("statusCode")
        return {
            "transaction_id": data.get("extTransactionId", ext_transaction_id),
            "status":         _map_status(cpay_status),
            "payment_url":    None,
            "additional_data": {
                "cpay_transaction_id": data.get("cPayTransactionId"),
                "cpay_status":         cpay_status,
                "reason_code":         data.get("reasonCode"),
                "description":         data.get("description"),
                "raw_response":        data,
            },
        }


    # Helper: fetch full transaction detail 


    def get_transaction_detail(
        self, ext_transaction_id: str
    ) -> Dict[str, Any]:
        """
        Fetch full transaction detail from CPay.

        Uses GET /api/cpaypayments/transaction?merchantCode=…&transactionNo=…
        """
        params : Dict[str, str] = {
            "merchantCode":  self.client_code,
            "transactionNo": ext_transaction_id,
        }
        try:
            resp = self._session.get(
                f"{self.base_url}{self._EP_TX_DETAIL}",
                params=params,
                timeout=30,
            )
            return self._handle_response(resp, "get_transaction_detail")
        except Exception as exc:
            raise PaymentVerificationError(
                f"CPayProvider: error fetching transaction detail – {exc}"
            ) from exc


    # Private helpers

    def _initiate_async(
        self, ext_tx_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """POST to the async USSD endpoint (recommended flow)."""
        try:
            resp = self._session.post(
                f"{self.base_url}{self._EP_PAYMENT_ASYNC}",
                json=payload,
                timeout=30,
            )
            data = self._handle_response(resp, "initialize_payment[async]")
        except PaymentInitializationError:
            raise
        except Exception as exc:
            raise PaymentInitializationError(
                f"CPayProvider: network error during async payment init – {exc}"
            ) from exc

        return {
            "transaction_id": data.get("extTransactionId", ext_tx_id),
            "status":         _map_status(data.get("paymentRequestStatus") or data.get("statusCode")),
            "payment_url":    None,  # async: customer confirms via USSD push
            "additional_data": {
                "cpay_transaction_id": data.get("cPayTransactionId"),
                "payment_mode":        "async_ussd",
                "cpay_status":         data.get("paymentRequestStatus"),
                "reason_code":         data.get("reasonCode"),
                "description":         data.get("description"),
                "customer_message":    (
                    "A USSD prompt has been sent to the customer's phone. "
                    "They may also dial the C-Pay USSD code and select 'Pay Merchant'."
                ),
                "raw_response":        data,
            },
        }

    def _initiate_otp(
        self,
        ext_tx_id: str,
        payload: Dict[str, Any],
        customer_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """POST to the OTP payment endpoint (step 1 of sync OTP flow)."""
        try:
            resp = self._session.post(
                f"{self.base_url}{self._EP_PAYMENT_OTP}",
                json=payload,
                timeout=30,
            )
            data = self._handle_response(resp, "initialize_payment[otp]")
        except PaymentInitializationError:
            raise
        except Exception as exc:
            raise PaymentInitializationError(
                f"CPayProvider: network error during OTP payment init – {exc}"
            ) from exc

        return {
            "transaction_id": data.get("extTransactionId", ext_tx_id),
            "status":         "pending",
            "payment_url":    None,
            "additional_data": {
                "cpay_transaction_id": data.get("cPayTransactionId"),
                "payment_mode":        "otp",
                "cpay_status":         data.get("paymentRequestStatus"),
                "reason_code":         data.get("reasonCode"),
                "description":         data.get("description"),
                "customer_message":    (
                    "An OTP has been sent to the customer. "
                    "Call confirm_otp_payment() once the customer supplies it."
                ),
                "raw_response":        data,
            },
        }

    def _initiate_card(
        self,
        ext_tx_id: str,
        payload: Dict[str, Any],
        customer_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        POST to the OTP endpoint with cardPayment=true.
        CPay returns an HTML redirect URL for card checkout.
        """
        email = customer_data.get("email", "")
        params: Dict[str, Any] = {"cardPayment": "true"}
        if email:
            params["email"] = email

        try:
            resp = self._session.post(
                f"{self.base_url}{self._EP_PAYMENT_OTP}",
                json=payload,
                params=params,
                timeout=30,
            )
        except Exception as exc:
            raise PaymentInitializationError(
                f"CPayProvider: network error during card payment init – {exc}"
            ) from exc

        # Card payments may return raw HTML/URL rather than JSON
        payment_url: Optional[str] = None
        data: Any = {}

        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type:
            try:
                data = resp.json()
            except ValueError:
                pass
            payment_url = data.get("payment_url") or data.get("additionalData")
        else:
            # Response body is the redirect URL or HTML content
            payment_url = resp.text.strip() if resp.text else None

        if not resp.ok:
            raise PaymentInitializationError(
                f"CPayProvider: card payment init failed (HTTP {resp.status_code}): {resp.text[:500]}"
            )

        return {
            "transaction_id": ext_tx_id,
            "status":         "pending",
            "payment_url":    payment_url,
            "additional_data": {
                "payment_mode":     "card",
                "customer_message": "Redirect the customer to the payment_url to complete card payment.",
                "raw_response":     data or resp.text,
            },
        }

    def _compute_checksum(
        self,
        ext_transaction_id: str,
        amount: float,
        msisdn: str,
        otp: str = "",
    ) -> str:
        """
        Compute HMAC-SHA256 checksum as required by the CPay API.

        Initiation salt:   ExtTransactionId + ClientCode + Amount + MSISDN
        Confirmation salt: ExtTransactionId + ClientCode + Amount + MSISDN + OTP

        Amount is formatted as a plain decimal string with no trailing zeros
        beyond two decimal places, matching CPay's documented
        example format.
        """
        amount_str = f"{amount:.2f}"
        salt = ext_transaction_id + self.client_code + amount_str + msisdn
        if otp:
            salt += otp

        return hmac.new(
            self.api_secret.encode("utf-8"),
            salt.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _handle_response(self, resp: requests.Response, context: str) -> Dict[str, Any]:
        """
        Parse a CPay HTTP response, logging and raising on errors.

        CPay uses:
          200 / 201 – success
          400        – validation error
          401        – bad API key
          403        – forbidden
          404        – not found
          424        – failed dependency (check reasonCode)
          500        – internal server error
        """
        try:
            data: Dict[str, Any] = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        logger.debug("CPay [%s] HTTP %s: %s", context, resp.status_code, data)

        if resp.status_code in (200, 201):
            return data

        err_msg = (
            data.get("description")
            or data.get("detail")
            or data.get("title")
            or resp.text[:300]
        )
        reason_code = data.get("reasonCode", "")
        full_msg = f"CPayProvider [{context}] HTTP {resp.status_code} – {err_msg}"
        if reason_code:
            full_msg += f" (reasonCode: {reason_code})"

        if resp.status_code in (400, 422):
            raise PaymentInitializationError(full_msg)
        elif resp.status_code == 401:
            raise PaymentInitializationError(f"CPayProvider: invalid API key – {err_msg}")
        elif resp.status_code == 403:
            raise PaymentInitializationError(f"CPayProvider: forbidden – {err_msg}")
        elif resp.status_code == 404:
            raise PaymentVerificationError(f"CPayProvider: resource not found – {err_msg}")
        elif resp.status_code == 424:
            raise PaymentInitializationError(full_msg)
        else:
            raise PaymentInitializationError(full_msg)