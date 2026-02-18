"""
M-Pesa Payment Provider
Based on the Safaricom Daraja API (v1 / v2).

Supported flows
---------------
STK Push (Lipa na M-Pesa Online)  – default / recommended for C2B
    POST /mpesa/stkpush/v1/processrequest
    POST /mpesa/stkpushquery/v1/query         (status poll)

C2B (till / paybill, server-to-server confirmation)
    POST /mpesa/c2b/v1/registerurl
    POST /mpesa/c2b/v1/simulate               (sandbox only)

B2C (business to customer / disbursements / refunds)
    POST /mpesa/b2c/v1/paymentrequest

Transaction Status (generic query)
    POST /mpesa/transactionstatus/v1/query

Reversal
    POST /mpesa/reversal/v1/request

Authentication
    GET  /oauth/v1/generate?grant_type=client_credentials  (Basic auth)
    Tokens are cached in-memory and refreshed automatically on expiry.

Webhook / callback
    Safaricom POSTs a signed JSON payload to your CallBackURL / ResultURL.
    verify_webhook_signature() validates the optional X-Daraja-Signature header.

Required config keys
--------------------
    consumer_key        – From Safaricom Developer Portal app
    consumer_secret     – From Safaricom Developer Portal app
    shortcode           – Business shortcode (PayBill or Buy-Goods)
    passkey             – Lipa na M-Pesa Online passkey (for STK Push)
    environment         – "sandbox" (default) | "production"

Optional config keys
--------------------
    initiator_name      – API operator username (for B2C / reversal)
    security_credential – RSA-encrypted initiator password (for B2C / reversal)
    callback_url        – Your publicly accessible STK Push callback endpoint
    result_url          – B2C / reversal result endpoint
    queue_timeout_url   – B2C / reversal timeout endpoint
    transaction_type    – "CustomerPayBillOnline" (default) | "CustomerBuyGoodsOnline"
    identifier_type     – Shortcode type: "1" paybill, "2" till, "4" MSISDN (default "4")
"""

import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from app.providers.base import (
    PaymentProvider,
    PaymentInitializationError,
    PaymentVerificationError,
    RefundError
)

logger = logging.getLogger(__name__)

# Daraja base URLs
_BASE_URLS = {
    "sandbox":    "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}


# M-Pesa result-code → internal status mapping
_RESULT_CODE_MAP: Dict[str, str] = {
    "0":  "completed",   # Success
    "1":  "failed",      # Insufficient funds
    "17": "failed",      # Financial limit reached
    "20": "failed",      # Transaction expired
    "26": "failed",      # Traffic/system timeout
    "32": "failed",      # Access denied
    "1032": "failed",    # Request cancelled by user
    "1037": "failed",    # USSD timeout
    "2001": "failed",    # Wrong PIN
}

# paymentRequestStatus values that appear in STK query responses
_STK_STATUS_MAP: Dict[str, str] = {
    "0":    "completed",
    "1":    "pending",
    "1032": "failed",
    "1037": "failed",
}


def _map_result_code(code: Any) -> str:
    return _RESULT_CODE_MAP.get(str(code), "pending")


# Provider

class MPesaProvider(PaymentProvider):
    """M-Pesa (Daraja API) payment provider adapter."""

    # Daraja endpoint paths
    _EP_AUTH          = "/oauth/v1/generate"
    _EP_STK_PUSH      = "/mpesa/stkpush/v1/processrequest"
    _EP_STK_QUERY     = "/mpesa/stkpushquery/v1/query"
    _EP_C2B_REGISTER  = "/mpesa/c2b/v1/registerurl"
    _EP_C2B_SIMULATE  = "/mpesa/c2b/v1/simulate"
    _EP_B2C           = "/mpesa/b2c/v1/paymentrequest"
    _EP_TX_STATUS     = "/mpesa/transactionstatus/v1/query"
    _EP_REVERSAL      = "/mpesa/reversal/v1/request"
    _EP_BALANCE       = "/mpesa/accountbalance/v1/query"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.consumer_key    = config.get("consumer_key", "")
        self.consumer_secret = config.get("consumer_secret", "")
        self.shortcode       = str(config.get("shortcode", ""))
        self.passkey         = config.get("passkey", "")
        self.environment     = config.get("environment", "sandbox").lower()

        # Optional – needed only for B2C / reversal / status queries
        self.initiator_name       = config.get("initiator_name", "")
        self.security_credential  = config.get("security_credential", "")
        self.callback_url         = config.get("callback_url", "")
        self.result_url           = config.get("result_url", "")
        self.queue_timeout_url    = config.get("queue_timeout_url", "")
        self.transaction_type     = config.get("transaction_type", "CustomerPayBillOnline")
        self.identifier_type      = config.get("identifier_type", "4")

        if not self.consumer_key or not self.consumer_secret:
            raise ValueError("MPesaProvider: 'consumer_key' and 'consumer_secret' are required")
        if self.environment not in _BASE_URLS:
            raise ValueError(f"MPesaProvider: environment must be 'sandbox' or 'production', got '{self.environment}'")

        self.base_url = _BASE_URLS[self.environment]

        # Token cache
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # PaymentProvider ABC

    def initialize_payment(
        self,
        amount: float,
        currency: str,
        customer_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiate an M-Pesa payment.

        customer_data required fields:
            phone              – Customer phone in international format, e.g. "254712345678"

        customer_data optional fields:
            account_reference  – Account / order reference shown on customer's phone (default: shortcode)
            transaction_desc   – Description shown on customer's phone (default: "Payment")
            payment_mode       – "stk" (default) | "c2b_simulate" (sandbox only)

        metadata optional:
            account_reference, transaction_desc, payment_mode

        Returns standard PaymentProvider dict:
            transaction_id  – CheckoutRequestID (STK) or ConversationID (C2B)
            status          – "pending"
            payment_url     – None (M-Pesa is push-based)
            additional_data – Full Daraja response + helper fields
        """
        metadata = metadata or {}
        phone    = self._normalise_phone(
            customer_data.get("phone") or customer_data.get("msisdn", "")
        )
        if not phone:
            raise PaymentInitializationError("MPesaProvider: 'phone' is required in customer_data")

        mode = (
            customer_data.get("payment_mode")
            or metadata.get("payment_mode", "stk")
        ).lower()

        account_ref  = (
            customer_data.get("account_reference")
            or metadata.get("account_reference", self.shortcode)
        )
        tx_desc = (
            customer_data.get("transaction_desc")
            or metadata.get("transaction_desc", "Payment")
        )

        if mode == "stk":
            return self._stk_push(amount, phone, account_ref, tx_desc)
        elif mode == "c2b_simulate":
            if self.environment != "sandbox":
                raise PaymentInitializationError(
                    "MPesaProvider: c2b_simulate is only available in the sandbox environment"
                )
            return self._c2b_simulate(amount, phone, account_ref)
        else:
            raise PaymentInitializationError(
                f"MPesaProvider: unknown payment_mode '{mode}'. Use 'stk' or 'c2b_simulate'."
            )

    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:
        """
        Query the status of an STK Push transaction using CheckoutRequestID.

        For B2C / generic transactions, use verify_transaction_status() instead
        (it requires a Daraja TransactionID, not a CheckoutRequestID).

        Returns standard PaymentProvider dict.
        """
        timestamp, password = self._generate_password()
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password":          password,
            "Timestamp":         timestamp,
            "CheckoutRequestID": provider_transaction_id,
        }

        try:
            resp = self._post(self._EP_STK_QUERY, payload, context="verify_payment")
        except Exception as exc:
            raise PaymentVerificationError(
                f"MPesaProvider: STK query failed – {exc}"
            ) from exc

        result_code = str(resp.get("ResultCode", ""))
        mpesa_status = resp.get("ResultDesc", "")
        internal_status = _STK_STATUS_MAP.get(result_code, "pending")

        return {
            "status":   internal_status,
            "amount":   None,   # not returned by STK query
            "currency": "KES",
            "additional_data": {
                "checkout_request_id":  resp.get("CheckoutRequestID"),
                "merchant_request_id":  resp.get("MerchantRequestID"),
                "result_code":          result_code,
                "result_desc":          mpesa_status,
                "raw_response":         resp,
            },
        }

    def refund_payment(
        self,
        provider_transaction_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reverse an M-Pesa transaction (Daraja Reversal API).

        provider_transaction_id – M-Pesa Transaction ID (e.g. "OEI2AK4Q16")
        amount                  – Amount to reverse; None reverses the full amount
        reason                  – Optional remarks

        Requires initiator_name, security_credential, result_url,
        and queue_timeout_url in config.

        Note: Reversal is asynchronous. The result is delivered to result_url.
        Returns "pending" status; listen for the callback to confirm.
        """
        self._assert_initiator_config("refund_payment")

        payload = {
            "Initiator":            self.initiator_name,
            "SecurityCredential":   self.security_credential,
            "CommandID":            "TransactionReversal",
            "TransactionID":        provider_transaction_id,
            "Amount":               str(int(amount)) if amount else "",
            "ReceiverParty":        self.shortcode,
            "RecieverIdentifierType": "4",
            "ResultURL":            self.result_url,
            "QueueTimeOutURL":      self.queue_timeout_url,
            "Remarks":              reason or "Refund",
            "Occasion":             "",
        }

        try:
            resp = self._post(self._EP_REVERSAL, payload, context="refund_payment")
        except Exception as exc:
            raise RefundError(f"MPesaProvider: reversal request failed – {exc}") from exc

        return {
            "refund_id":  resp.get("ConversationID", provider_transaction_id),
            "status":     "pending",   # async; result arrives at result_url
            "amount":     amount,
            "currency":   "KES",
            "reason":     reason,
            "additional_data": {
                "conversation_id":          resp.get("ConversationID"),
                "originator_conversation_id": resp.get("OriginatorConversationID"),
                "response_description":     resp.get("ResponseDescription"),
                "response_code":            resp.get("ResponseCode"),
                "raw_response":             resp,
            },
        }

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify the optional X-Daraja-Signature header Safaricom attaches
        to callback POSTs in some API versions.

        Safaricom signs payloads with HMAC-SHA256 using your consumer_secret.
        If the signature header is absent (common in v1 callbacks), this method
        returns True and relies on structural payload validation in handle_webhook().

        Args:
            payload   – Raw request body bytes
            signature – Value of the X-Daraja-Signature header (may be empty)
        """
        if not signature:
            # Safaricom v1 callbacks don't carry a signature header.
            # Caller should validate the source IP or cross-check with verify_payment().
            logger.debug(
                "MPesaProvider.verify_webhook_signature: no signature header present; "
                "returning True. Validate payload contents via verify_payment()."
            )
            return True

        expected = hmac.new(
            self.consumer_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        try:
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an M-Pesa callback / result notification.

        Handles three callback shapes:
          1. STK Push callback  (Body.stkCallback)
          2. B2C result         (Result)
          3. C2B confirmation   (flat body with TransID / Amount etc.)
        """
        # ── STK Push callback
        stk = (
            payload.get("Body", {})
                   .get("stkCallback", {})
        )
        if stk:
            return self._handle_stk_callback(stk)

        # ── B2C / Reversal / Transaction-Status result 
        result = payload.get("Result", {})
        if result:
            return self._handle_result_callback(result)

        # ── C2B confirmation / validation 
        if "TransID" in payload or "BillRefNumber" in payload:
            return self._handle_c2b_callback(payload)

        # Unknown shape – return raw
        logger.warning("MPesaProvider.handle_webhook: unrecognised payload shape: %s", list(payload.keys()))
        return {
            "transaction_id": payload.get("TransID") or payload.get("CheckoutRequestID", ""),
            "event_type":     "payment.unknown",
            "status":         "pending",
            "additional_data": {"raw_payload": payload},
        }

    # Extra public helpers (B2C disbursements, C2B registration, etc.)

    def disburse_b2c(
        self,
        amount: float,
        phone: str,
        command_id: str = "BusinessPayment",
        remarks: str = "Disbursement",
        occasion: str = "",
    ) -> Dict[str, Any]:
        """
        Send money from your business to a customer (B2C).

        command_id options:
            "SalaryPayment"   – Salary / payroll
            "BusinessPayment" – Ad-hoc business payment (default)
            "PromotionPayment"– Promotions / rewards

        Returns a pending result; the final outcome is delivered to result_url.
        """
        self._assert_initiator_config("disburse_b2c")

        payload = {
            "InitiatorName":      self.initiator_name,
            "SecurityCredential": self.security_credential,
            "CommandID":          command_id,
            "Amount":             str(int(amount)),
            "PartyA":             self.shortcode,
            "PartyB":             self._normalise_phone(phone),
            "Remarks":            remarks,
            "QueueTimeOutURL":    self.queue_timeout_url,
            "ResultURL":          self.result_url,
            "Occasion":           occasion,
        }

        resp = self._post(self._EP_B2C, payload, context="disburse_b2c")

        return {
            "transaction_id": resp.get("ConversationID", ""),
            "status":         "pending",
            "payment_url":    None,
            "additional_data": {
                "conversation_id":            resp.get("ConversationID"),
                "originator_conversation_id": resp.get("OriginatorConversationID"),
                "response_code":              resp.get("ResponseCode"),
                "response_description":       resp.get("ResponseDescription"),
                "raw_response":               resp,
            },
        }

    def register_c2b_urls(
        self,
        confirmation_url: str,
        validation_url: str,
        response_type: str = "Completed",
    ) -> Dict[str, Any]:
        """
        Register C2B confirmation and validation URLs with Safaricom.

        Must be called once per shortcode before going live.
        response_type: "Completed" (auto-accept) | "Cancelled" (validate first).
        """
        payload = {
            "ShortCode":       self.shortcode,
            "ResponseType":    response_type,
            "ConfirmationURL": confirmation_url,
            "ValidationURL":   validation_url,
        }
        return self._post(self._EP_C2B_REGISTER, payload, context="register_c2b_urls")

    def verify_transaction_status(
        self,
        transaction_id: str,
        remarks: str = "Status query",
        occasion: str = "",
    ) -> Dict[str, Any]:
        """
        Query the status of any M-Pesa transaction by its TransactionID.

        Different from verify_payment() which uses CheckoutRequestID (STK only).
        Result is delivered asynchronously to result_url.
        """
        self._assert_initiator_config("verify_transaction_status")

        payload = {
            "Initiator":          self.initiator_name,
            "SecurityCredential": self.security_credential,
            "CommandID":          "TransactionStatusQuery",
            "TransactionID":      transaction_id,
            "PartyA":             self.shortcode,
            "IdentifierType":     self.identifier_type,
            "ResultURL":          self.result_url,
            "QueueTimeOutURL":    self.queue_timeout_url,
            "Remarks":            remarks,
            "Occasion":           occasion,
        }

        resp = self._post(self._EP_TX_STATUS, payload, context="verify_transaction_status")

        return {
            "status": "pending",   # async; result comes to result_url
            "additional_data": {
                "conversation_id":            resp.get("ConversationID"),
                "originator_conversation_id": resp.get("OriginatorConversationID"),
                "response_code":              resp.get("ResponseCode"),
                "response_description":       resp.get("ResponseDescription"),
                "raw_response":               resp,
            },
        }

    # Private – payment flows

    def _stk_push(
        self,
        amount: float,
        phone: str,
        account_reference: str,
        transaction_desc: str,
    ) -> Dict[str, Any]:
        """Initiate a Lipa na M-Pesa Online (STK Push) payment."""
        if not self.passkey:
            raise PaymentInitializationError("MPesaProvider: 'passkey' is required for STK Push")
        if not self.callback_url:
            raise PaymentInitializationError("MPesaProvider: 'callback_url' is required for STK Push")

        timestamp, password = self._generate_password()

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password":          password,
            "Timestamp":         timestamp,
            "TransactionType":   self.transaction_type,
            "Amount":            str(int(amount)),  
            "PartyA":            phone,
            "PartyB":            self.shortcode,
            "PhoneNumber":       phone,
            "CallBackURL":       self.callback_url,
            "AccountReference":  account_reference[:12],  
            "TransactionDesc":   transaction_desc[:13], 
        }

        try:
            resp = self._post(self._EP_STK_PUSH, payload, context="stk_push")
        except Exception as exc:
            raise PaymentInitializationError(
                f"MPesaProvider: STK Push failed – {exc}"
            ) from exc

        return {
            "transaction_id": resp.get("CheckoutRequestID", ""),
            "status":         "pending",
            "payment_url":    None,
            "additional_data": {
                "checkout_request_id":  resp.get("CheckoutRequestID"),
                "merchant_request_id":  resp.get("MerchantRequestID"),
                "response_code":        resp.get("ResponseCode"),
                "response_description": resp.get("ResponseDescription"),
                "customer_message":     resp.get("CustomerMessage"),
                "payment_mode":         "stk_push",
                "raw_response":         resp,
            },
        }

    def _c2b_simulate(
        self, amount: float, phone: str, bill_ref: str
    ) -> Dict[str, Any]:
        """Simulate a C2B payment (sandbox only)."""
        payload = {
            "ShortCode":     self.shortcode,
            "CommandID":     "CustomerPayBillOnline",
            "Amount":        str(int(amount)),
            "Msisdn":        phone,
            "BillRefNumber": bill_ref,
        }

        try:
            resp = self._post(self._EP_C2B_SIMULATE, payload, context="c2b_simulate")
        except Exception as exc:
            raise PaymentInitializationError(
                f"MPesaProvider: C2B simulate failed – {exc}"
            ) from exc

        return {
            "transaction_id": resp.get("ConversationID", ""),
            "status":         "pending",
            "payment_url":    None,
            "additional_data": {
                "conversation_id":      resp.get("ConversationID"),
                "originator_id":        resp.get("OriginatorConversationID"),
                "response_code":        resp.get("ResponseCode"),
                "response_description": resp.get("ResponseDescription"),
                "payment_mode":         "c2b_simulate",
                "raw_response":         resp,
            },
        }

    # Private – webhook handlers

    def _handle_stk_callback(self, stk: Dict[str, Any]) -> Dict[str, Any]:
        """Parse STK Push callback body."""
        result_code  = str(stk.get("ResultCode", ""))
        checkout_id  = stk.get("CheckoutRequestID", "")
        merchant_id  = stk.get("MerchantRequestID", "")
        internal_status = _map_result_code(result_code)

        # Extract CallbackMetadata items into a flat dict
        meta: Dict[str, Any] = {}
        for item in (
            stk.get("CallbackMetadata", {}).get("Item", [])
        ):
            meta[item.get("Name", "")] = item.get("Value")

        return {
            "transaction_id": checkout_id,
            "event_type":     f"payment.{'completed' if internal_status == 'completed' else 'failed'}",
            "status":         internal_status,
            "additional_data": {
                "checkout_request_id":  checkout_id,
                "merchant_request_id":  merchant_id,
                "result_code":          result_code,
                "result_desc":          stk.get("ResultDesc"),
                "mpesa_receipt_number": meta.get("MpesaReceiptNumber"),
                "amount":               meta.get("Amount"),
                "phone_number":         meta.get("PhoneNumber"),
                "transaction_date":     meta.get("TransactionDate"),
                "raw_callback":         stk,
            },
        }

    def _handle_result_callback(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse B2C / Reversal / TransactionStatus result callback."""
        result_code     = str(result.get("ResultCode", ""))
        internal_status = _map_result_code(result_code)
        transaction_id  = result.get("ConversationID", "")
        result_type     = result.get("ResultType", "")

        # Flatten ResultParameters
        params: Dict[str, Any] = {}
        for item in (
            result.get("ResultParameters", {}).get("ResultParameter", [])
        ):
            params[item.get("Key", "")] = item.get("Value")

        # Determine event type from CommandID if present
        command = result.get("ReferenceData", {}).get("ReferenceItem", {}).get("Value", "")
        if "Reversal" in command:
            event_type = "payment.reversed" if internal_status == "completed" else "reversal.failed"
        elif "Status" in command:
            event_type = f"transaction.status.{internal_status}"
        else:
            event_type = f"payment.{'completed' if internal_status == 'completed' else 'failed'}"

        return {
            "transaction_id": transaction_id,
            "event_type":     event_type,
            "status":         internal_status,
            "additional_data": {
                "conversation_id":            result.get("ConversationID"),
                "originator_conversation_id": result.get("OriginatorConversationID"),
                "result_code":                result_code,
                "result_desc":                result.get("ResultDesc"),
                "result_type":                result_type,
                "transaction_id_mpesa":       params.get("TransactionID"),
                "amount":                     params.get("TransactionAmount"),
                "receiver_party_name":        params.get("ReceiverPartyPublicName"),
                "completed_at":               params.get("TransactionCompletedDateTime"),
                "b2c_charges":                params.get("B2CChargesPaidAccountFunds"),
                "result_params":              params,
                "raw_callback":               result,
            },
        }

    def _handle_c2b_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a C2B confirmation / validation payload."""
        return {
            "transaction_id": payload.get("TransID", ""),
            "event_type":     "payment.completed",
            "status":         "completed",
            "additional_data": {
                "transaction_type":  payload.get("TransactionType"),
                "trans_id":          payload.get("TransID"),
                "trans_time":        payload.get("TransTime"),
                "amount":            payload.get("TransAmount"),
                "business_shortcode": payload.get("BusinessShortCode"),
                "bill_ref_number":   payload.get("BillRefNumber"),
                "invoice_number":    payload.get("InvoiceNumber"),
                "org_account_balance": payload.get("OrgAccountBalance"),
                "third_party_trans_id": payload.get("ThirdPartyTransID"),
                "msisdn":            payload.get("MSISDN"),
                "first_name":        payload.get("FirstName"),
                "last_name":         payload.get("LastName"),
                "raw_callback":      payload,
            },
        }

    # Private – auth & HTTP helpers

    def _get_access_token(self) -> str | None:
        """Return a valid OAuth access token, refreshing if expired."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = f"{self.base_url}{self._EP_AUTH}?grant_type=client_credentials"
        try:
            resp = requests.get(
                url,
                auth=(self.consumer_key, self.consumer_secret),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise PaymentInitializationError(
                f"MPesaProvider: failed to obtain access token – {exc}"
            ) from exc

        self._access_token = data.get("access_token", "")
        # Safaricom tokens expire in 3600s; cache with a 60s safety margin
        expires_in = int(data.get("expires_in", 3600))
        self._token_expiry = time.time() + expires_in - 60

        logger.debug("MPesaProvider: access token refreshed (expires in %ds)", expires_in)
        return self._access_token

    def _post(
        self, endpoint: str, payload: Dict[str, Any], context: str = ""
    ) -> Dict[str, Any]:
        """Execute an authenticated POST to a Daraja endpoint."""
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }

        url = f"{self.base_url}{endpoint}"
        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise PaymentInitializationError(
                f"MPesaProvider [{context}]: network error – {exc}"
            ) from exc

        return self._handle_response(resp, context)

    def _handle_response(
        self, resp: requests.Response, context: str
    ) -> Dict[str, Any]:
        """Parse Daraja response, raising on error codes."""
        try:
            data: Dict[str, Any] = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        logger.debug("MPesa [%s] HTTP %s: %s", context, resp.status_code, data)

        # Daraja sometimes returns 200 with an error in the body
        error_code = data.get("errorCode") or data.get("ResultCode")
        error_msg  = (
            data.get("errorMessage")
            or data.get("ResponseDescription")
            or data.get("ResultDesc")
            or resp.text[:300]
        )

        if not resp.ok:
            raise PaymentInitializationError(
                f"MPesaProvider [{context}] HTTP {resp.status_code}: {error_msg}"
            )

        # Daraja error codes in 200 responses (e.g. "500.001.1001")
        if error_code and str(error_code).startswith(("500", "400", "401")):
            raise PaymentInitializationError(
                f"MPesaProvider [{context}] Daraja error {error_code}: {error_msg}"
            )

        return data

    def _generate_password(self):
        """
        Generate the STK Push password and timestamp.

        Password = Base64(BusinessShortCode + Passkey + Timestamp)
        Timestamp = YYYYMMDDHHmmss (Nairobi time is fine for sandbox; use UTC for production)
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        return timestamp, password

    @staticmethod
    def _normalise_phone(phone: str) -> str:
        """
        Normalise a phone number to Safaricom's expected format (2547XXXXXXXX).

        Accepts: +254712345678, 0712345678, 254712345678, 712345678
        """
        if not phone:
            return ""
        phone = str(phone).strip().replace(" ", "").replace("-", "")
        if phone.startswith("+"):
            phone = phone[1:]
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        if not phone.startswith("254"):
            phone = "254" + phone
        return phone

    def _assert_initiator_config(self, context: str) -> None:
        """Raise if initiator credentials are not configured."""
        missing = []
        if not self.initiator_name:
            missing.append("initiator_name")
        if not self.security_credential:
            missing.append("security_credential")
        if not self.result_url:
            missing.append("result_url")
        if not self.queue_timeout_url:
            missing.append("queue_timeout_url")
        if missing:
            raise PaymentInitializationError(
                f"MPesaProvider [{context}]: missing config – {', '.join(missing)}"
            )