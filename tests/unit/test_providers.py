"""
Unit Tests for Payment Providers
=================================
Updated to match the REAL MPesaProvider and CPayProvider implementations.

Change summary vs. the old mock-based tests
--------------------------------------------

MPesaProvider:
  - No SANDBOX_BASE_URL / PRODUCTION_BASE_URL class constants.
    base_url is resolved from the module-level _BASE_URLS dict at init time.
  - Phone numbers are auto-normalised; passing a local-format number (0712...)
    is NOT an error in the real provider.
  - Currency is NOT validated; the provider accepts any currency string.
  - refund_payment() is async (Reversal API) and requires initiator config.
  - All HTTP calls go through self._session.post / requests.get — mock at
    those exact targets (see patch paths below).
  - Token caching: patch requests.get for OAuth; patch provider._session.post
    for all Daraja business endpoints.

CPayProvider:
  - __init__ now requires client_code in addition to api_key / api_secret.
  - All operations hit real HTTP (no in-memory mock store).
    Mock provider._session.get / provider._session.post on the instance.
  - verify_payment() returns amount=None, currency=None (not echoed by the
    /transaction-status endpoint).
  - refund_payment() unconditionally raises RefundError (no refund API in v1.1).
  - verify_webhook_signature() always returns True.
  - handle_webhook() consumes a FLAT TransactionResponse payload
    (paymentRequestStatus / extTransactionId / cPayTransactionId ...),
    NOT the old nested event/data shape.
  - simulate_webhook_callback() class method is REMOVED.

Services (payment_service, webhook_service, audit_service, idempotency)
are NOT changed – they mock get_provider() at a high level and are
entirely unaffected by these provider implementation changes.

Stripe tests are unchanged from the original (StripeProvider is unmodified).
"""

import json
import pytest
from unittest.mock import Mock, patch

from app.providers.base import (
    PaymentInitializationError,
    PaymentVerificationError,
    RefundError,
)
from app.providers.mpesa_provider import MPesaProvider, _BASE_URLS
from app.providers.cpay_provider import CPayProvider


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _mock_http_response(json_data: dict, status_code: int = 200) -> Mock:
    """Return a mock requests.Response whose .json() returns json_data."""
    resp = Mock()
    resp.ok = 200 <= status_code < 400
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data)
    resp.headers = {"Content-Type": "application/json"}
    return resp


def _daraja_token_resp() -> Mock:
    """Valid Daraja OAuth token response (expires in ~1 hour)."""
    return _mock_http_response({"access_token": "daraja_tok_abc", "expires_in": "3599"})


# ===========================================================================
# MPesaProvider
# ===========================================================================

class TestMPesaProvider:
    """Tests for the real M-Pesa (Daraja API) provider."""

    # ── fixtures ──────────────────────────────────────────────────────────

    @pytest.fixture
    def base_config(self):
        return {
            "environment":       "sandbox",
            "consumer_key":      "test_consumer_key",
            "consumer_secret":   "test_consumer_secret",
            "shortcode":         "174379",
            "passkey":           "test_passkey",
            "callback_url":      "https://example.com/mpesa/callback",
            "result_url":        "https://example.com/mpesa/result",
            "queue_timeout_url": "https://example.com/mpesa/timeout",
        }

    @pytest.fixture
    def provider(self, base_config):
        return MPesaProvider(base_config)

    @pytest.fixture
    def provider_with_initiator(self, base_config):
        """Provider configured to execute B2C / reversal flows."""
        return MPesaProvider({
            **base_config,
            "initiator_name":      "testapi",
            "security_credential": "encrypted_cred_b64==",
        })

    # ── initialisation ────────────────────────────────────────────────────

    def test_initialization_sandbox(self, provider):
        assert provider.consumer_key    == "test_consumer_key"
        assert provider.consumer_secret == "test_consumer_secret"
        assert provider.shortcode       == "174379"
        assert provider.environment     == "sandbox"
        assert provider.base_url        == _BASE_URLS["sandbox"]
        assert provider.base_url        == "https://sandbox.safaricom.co.ke"

    def test_initialization_production_url(self, base_config):
        prod = MPesaProvider({**base_config, "environment": "production"})
        assert prod.base_url == _BASE_URLS["production"]
        assert prod.base_url == "https://api.safaricom.co.ke"

    def test_initialization_missing_consumer_key_raises(self):
        with pytest.raises(ValueError, match="consumer_key"):
            MPesaProvider({"consumer_key": "", "consumer_secret": "s"})

    def test_initialization_missing_consumer_secret_raises(self):
        with pytest.raises(ValueError, match="consumer_key"):
            MPesaProvider({"consumer_key": "k"})

    def test_initialization_invalid_environment_raises(self, base_config):
        with pytest.raises(ValueError, match="environment"):
            MPesaProvider({**base_config, "environment": "staging"})

    def test_optional_fields_default_to_empty(self, provider):
        assert provider.initiator_name      == ""
        assert provider.security_credential == ""
        assert provider.result_url          == ""
        assert provider.queue_timeout_url   == ""
        assert provider.transaction_type    == "CustomerPayBillOnline"
        assert provider.identifier_type     == "4"

    # ── phone normalisation ───────────────────────────────────────────────

    @pytest.mark.parametrize("raw, expected", [
        ("254712345678",    "254712345678"),  # already E.164
        ("+254712345678",   "254712345678"),  # strip leading +
        ("0712345678",      "254712345678"),  # local 07XX -> 2547XX
        ("712345678",       "254712345678"),  # 9-digit -> prepend 254
        ("254 712 345 678", "254712345678"),  # strip spaces
    ])
    def test_normalise_phone(self, raw, expected):
        assert MPesaProvider._normalise_phone(raw) == expected

    def test_normalise_phone_empty(self):
        assert MPesaProvider._normalise_phone("") == ""

    # ── initialize_payment – STK Push ─────────────────────────────────────

    def test_stk_push_success(self, provider):
        """Successful STK Push returns the correct dict shape."""
        token_resp = _daraja_token_resp()
        stk_resp   = _mock_http_response({
            "MerchantRequestID":  "mrq-001",
            "CheckoutRequestID":  "ws_CO_ABC123",
            "ResponseCode":       "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage":    "Success",
        })

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=stk_resp):

            result = provider.initialize_payment(
                amount=1500.00,
                currency="KES",
                customer_data={
                    "phone":             "254712345678",
                    "account_reference": "ORD-999",
                    "transaction_desc":  "Order payment",
                },
            )

        assert result["transaction_id"]                              == "ws_CO_ABC123"
        assert result["status"]                                      == "pending"
        assert result["payment_url"]                                 is None
        assert result["additional_data"]["merchant_request_id"]      == "mrq-001"
        assert result["additional_data"]["payment_mode"]             == "stk_push"
        assert result["additional_data"]["customer_message"]         == "Success"

    def test_stk_push_sends_normalised_phone(self, provider):
        """Local-format phone is normalised before sending to Daraja."""
        token_resp = _daraja_token_resp()
        stk_resp   = _mock_http_response({"CheckoutRequestID": "ws_CO_XYZ", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=stk_resp) as mock_post:

            provider.initialize_payment(
                amount=500.00,
                currency="KES",
                customer_data={"phone": "0712345678"},
            )

        body = mock_post.call_args[1]["json"]
        assert body["PhoneNumber"] == "254712345678"
        assert body["PartyA"]      == "254712345678"

    def test_account_reference_truncated_to_12_chars(self, provider):
        """AccountReference is capped at 12 chars per Daraja spec."""
        token_resp = _daraja_token_resp()
        stk_resp   = _mock_http_response({"CheckoutRequestID": "ws_CO_1", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=stk_resp) as mock_post:

            provider.initialize_payment(
                amount=100.00,
                currency="KES",
                customer_data={
                    "phone":             "254712345678",
                    "account_reference": "VERYLONGREFCODE999",  # > 12 chars
                },
            )

        body = mock_post.call_args[1]["json"]
        assert len(body["AccountReference"]) <= 12

    def test_non_kes_currency_accepted(self, provider):
        """Currency is not validated – the real provider accepts any value."""
        token_resp = _daraja_token_resp()
        stk_resp   = _mock_http_response({"CheckoutRequestID": "ws_CO_USD", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=stk_resp):
            # Must NOT raise – currency validation was only in the old mock
            result = provider.initialize_payment(
                amount=100.00,
                currency="USD",
                customer_data={"phone": "254712345678"},
            )

        assert result["status"] == "pending"

    def test_local_phone_format_not_rejected(self, provider):
        """Local-format phone (0712...) is normalised, NOT rejected with an exception."""
        token_resp = _daraja_token_resp()
        stk_resp   = _mock_http_response({"CheckoutRequestID": "ws_CO_LOC", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=stk_resp):
            # Old test expected an exception here – real provider normalises instead
            result = provider.initialize_payment(
                amount=100.00,
                currency="KES",
                customer_data={"phone": "0700000000"},
            )

        assert result["status"] == "pending"

    def test_missing_phone_raises(self, provider):
        with pytest.raises(PaymentInitializationError, match="phone"):
            provider.initialize_payment(amount=100.00, currency="KES", customer_data={})

    def test_unknown_payment_mode_raises(self, provider):
        with pytest.raises(PaymentInitializationError, match="unknown payment_mode"):
            provider.initialize_payment(
                amount=100.00,
                currency="KES",
                customer_data={"phone": "254712345678", "payment_mode": "instant"},
            )

    def test_c2b_simulate_raises_outside_sandbox(self, base_config):
        prod = MPesaProvider({**base_config, "environment": "production"})
        with pytest.raises(PaymentInitializationError, match="sandbox"):
            prod.initialize_payment(
                amount=100.00,
                currency="KES",
                customer_data={"phone": "254712345678", "payment_mode": "c2b_simulate"},
            )

    def test_c2b_simulate_in_sandbox(self, provider):
        """c2b_simulate mode POSTs to the C2B simulate endpoint."""
        token_resp = _daraja_token_resp()
        c2b_resp   = _mock_http_response({
            "ConversationID":          "conv-001",
            "OriginatorConversationID": "orig-001",
            "ResponseCode":            "0",
            "ResponseDescription":     "Accept the service request successfully.",
        })

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=c2b_resp) as mock_post:

            result = provider.initialize_payment(
                amount=200.00,
                currency="KES",
                customer_data={"phone": "254712345678", "payment_mode": "c2b_simulate"},
            )

        assert result["status"]                                    == "pending"
        assert result["additional_data"]["payment_mode"]           == "c2b_simulate"
        body = mock_post.call_args[1]["json"]
        assert body["CommandID"] == "CustomerPayBillOnline"

    def test_oauth_token_failure_raises(self, provider):
        with patch("requests.get", side_effect=ConnectionError("DNS failure")):
            with pytest.raises(PaymentInitializationError, match="access token"):
                provider.initialize_payment(
                    amount=100.00,
                    currency="KES",
                    customer_data={"phone": "254712345678"},
                )

    def test_daraja_http_4xx_raises(self, provider):
        token_resp = _daraja_token_resp()
        err_resp   = _mock_http_response(
            {"errorCode": "400.002.02", "errorMessage": "Bad Request"}, 400
        )

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=err_resp):
            with pytest.raises(PaymentInitializationError):
                provider.initialize_payment(
                    amount=100.00,
                    currency="KES",
                    customer_data={"phone": "254712345678"},
                )

    def test_oauth_token_is_cached(self, provider):
        """OAuth token is fetched once and reused for subsequent calls."""
        token_resp = _daraja_token_resp()
        stk_resp   = _mock_http_response({"CheckoutRequestID": "ws_CO_1", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp) as mock_get, \
             patch.object(provider._session, "post", return_value=stk_resp):

            provider.initialize_payment(
                amount=100.00, currency="KES",
                customer_data={"phone": "254712345678"},
            )
            provider.initialize_payment(
                amount=200.00, currency="KES",
                customer_data={"phone": "254712345678"},
            )

        # OAuth GET called exactly once despite two payment calls
        assert mock_get.call_count == 1

    # ── verify_payment ────────────────────────────────────────────────────

    def test_verify_payment_completed(self, provider):
        """ResultCode 0 maps to 'completed'."""
        token_resp  = _daraja_token_resp()
        query_resp  = _mock_http_response({
            "ResultCode":        "0",
            "ResultDesc":        "The service request is processed successfully.",
            "CheckoutRequestID": "ws_CO_ABC123",
            "MerchantRequestID": "mrq-001",
        })

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=query_resp):
            result = provider.verify_payment("ws_CO_ABC123")

        assert result["status"]                                     == "completed"
        assert result["currency"]                                   == "KES"
        assert result["additional_data"]["checkout_request_id"]     == "ws_CO_ABC123"
        assert result["additional_data"]["result_code"]             == "0"

    def test_verify_payment_pending(self, provider):
        """Unknown ResultCode defaults to 'pending'."""
        token_resp  = _daraja_token_resp()
        query_resp  = _mock_http_response({"ResultCode": "1", "ResultDesc": "Pending"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=query_resp):
            result = provider.verify_payment("ws_CO_PENDING")

        assert result["status"] == "pending"

    def test_verify_payment_user_cancelled(self, provider):
        """ResultCode 1032 (user cancelled) maps to 'failed'."""
        token_resp  = _daraja_token_resp()
        query_resp  = _mock_http_response({"ResultCode": "1032", "ResultDesc": "Cancelled"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=query_resp):
            result = provider.verify_payment("ws_CO_CANCEL")

        assert result["status"] == "failed"

    def test_verify_payment_network_error_raises(self, provider):
        token_resp = _daraja_token_resp()

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", side_effect=ConnectionError("timeout")):
            with pytest.raises(PaymentVerificationError):
                provider.verify_payment("ws_CO_FAIL")

    def test_verify_payment_returns_kes_currency(self, provider):
        """verify_payment always returns currency='KES' (hardcoded in provider)."""
        token_resp  = _daraja_token_resp()
        query_resp  = _mock_http_response({"ResultCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider._session, "post", return_value=query_resp):
            result = provider.verify_payment("ws_CO_1")

        assert result["currency"] == "KES"
        assert result["amount"]   is None  # not returned by STK query endpoint

    # ── refund_payment (reversal) ─────────────────────────────────────────

    def test_refund_requires_initiator_config(self, provider):
        """refund_payment raises with a clear message when initiator config is absent."""
        with pytest.raises(PaymentInitializationError, match="missing config"):
            provider.refund_payment("OEI2AK4Q16", amount=1000.00)

    def test_refund_success_returns_pending(self, provider_with_initiator):
        """Successful reversal request returns status='pending' (async result)."""
        token_resp    = _daraja_token_resp()
        reversal_resp = _mock_http_response({
            "ConversationID":           "conv-rev-001",
            "OriginatorConversationID": "orig-rev-001",
            "ResponseCode":             "0",
            "ResponseDescription":      "Accept the service request successfully.",
        })

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider_with_initiator._session, "post", return_value=reversal_resp):
            result = provider_with_initiator.refund_payment(
                provider_transaction_id="OEI2AK4Q16",
                amount=500.00,
                reason="Duplicate charge",
            )

        assert result["status"]                                == "pending"
        assert result["refund_id"]                             == "conv-rev-001"
        assert result["amount"]                                == 500.00
        assert result["currency"]                              == "KES"
        assert result["additional_data"]["conversation_id"]    == "conv-rev-001"

    def test_refund_full_amount_sends_empty_string(self, provider_with_initiator):
        """amount=None sends an empty Amount field to Daraja (full reversal)."""
        token_resp    = _daraja_token_resp()
        reversal_resp = _mock_http_response({"ConversationID": "conv-full", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider_with_initiator._session, "post", return_value=reversal_resp) as mock_post:
            provider_with_initiator.refund_payment("OEI2AK4Q16")

        body = mock_post.call_args[1]["json"]
        assert body["Amount"] == ""

    def test_refund_network_error_raises_refund_error(self, provider_with_initiator):
        token_resp = _daraja_token_resp()

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider_with_initiator._session, "post", side_effect=ConnectionError("down")):
            with pytest.raises(RefundError, match="reversal request failed"):
                provider_with_initiator.refund_payment("OEI2AK4Q16", amount=100.00)

    # ── verify_webhook_signature ──────────────────────────────────────────

    def test_verify_webhook_no_signature_returns_true(self, provider):
        """Safaricom v1 callbacks carry no signature; method returns True."""
        assert provider.verify_webhook_signature(b'{"Body": {}}', "") is True

    def test_verify_webhook_valid_hmac_returns_true(self, provider):
        import hashlib
        import hmac as _hmac
        payload = b'{"Body":{"stkCallback":{"ResultCode":0}}}'
        sig = _hmac.new(
            provider.consumer_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        assert provider.verify_webhook_signature(payload, sig) is True

    def test_verify_webhook_invalid_signature_returns_false(self, provider):
        assert provider.verify_webhook_signature(b'{"x":1}', "wrong_sig") is False

    # ── handle_webhook ────────────────────────────────────────────────────

    def test_handle_webhook_stk_success(self, provider):
        """STK Push success callback routes to 'completed'."""
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "mrq-001",
                    "CheckoutRequestID": "ws_CO_ABC123",
                    "ResultCode":        0,
                    "ResultDesc":        "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount",             "Value": 1500},
                            {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                            {"Name": "PhoneNumber",        "Value": 254712345678},
                            {"Name": "TransactionDate",    "Value": 20240101120000},
                        ]
                    },
                }
            }
        }
        result = provider.handle_webhook(payload)

        assert result["transaction_id"]                           == "ws_CO_ABC123"
        assert result["event_type"]                               == "payment.completed"
        assert result["status"]                                   == "completed"
        assert result["additional_data"]["mpesa_receipt_number"]  == "NLJ7RT61SV"
        assert result["additional_data"]["amount"]                == 1500
        assert result["additional_data"]["result_code"]           == "0"

    def test_handle_webhook_stk_user_cancelled(self, provider):
        payload = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": "ws_CO_CANCEL",
                    "ResultCode":        1032,
                    "ResultDesc":        "Request cancelled by user",
                }
            }
        }
        result = provider.handle_webhook(payload)

        assert result["status"]     == "failed"
        assert result["event_type"] == "payment.failed"

    def test_handle_webhook_b2c_result(self, provider):
        """B2C result callback is correctly parsed."""
        payload = {
            "Result": {
                "ResultType":   0,
                "ResultCode":   0,
                "ResultDesc":   "The service request is processed successfully.",
                "ConversationID": "conv-b2c-001",
                "OriginatorConversationID": "orig-b2c-001",
                "ResultParameters": {
                    "ResultParameter": [
                        {"Key": "TransactionAmount",           "Value": 200},
                        {"Key": "TransactionID",               "Value": "OEI2AK4Q16"},
                        {"Key": "ReceiverPartyPublicName",     "Value": "254712345678 - Test"},
                        {"Key": "TransactionCompletedDateTime","Value": "02.01.2024 12:00:00"},
                    ]
                },
            }
        }
        result = provider.handle_webhook(payload)

        assert result["status"]                               == "completed"
        assert result["transaction_id"]                       == "conv-b2c-001"
        assert result["additional_data"]["transaction_id_mpesa"] == "OEI2AK4Q16"
        assert result["additional_data"]["amount"]            == 200

    def test_handle_webhook_c2b_confirmation(self, provider):
        """Flat C2B confirmation payload maps to 'completed'."""
        payload = {
            "TransactionType":   "Pay Bill",
            "TransID":           "OEI2AK4Q16",
            "TransTime":         "20240101120000",
            "TransAmount":       "1500.00",
            "BusinessShortCode": "174379",
            "BillRefNumber":     "ORD-001",
            "MSISDN":            "254712345678",
            "FirstName":         "John",
            "LastName":          "Doe",
        }
        result = provider.handle_webhook(payload)

        assert result["transaction_id"]                     == "OEI2AK4Q16"
        assert result["event_type"]                         == "payment.completed"
        assert result["status"]                             == "completed"
        assert result["additional_data"]["bill_ref_number"] == "ORD-001"
        assert result["additional_data"]["first_name"]      == "John"

    def test_handle_webhook_unknown_shape(self, provider):
        result = provider.handle_webhook({"completely": "unknown"})
        assert result["event_type"] == "payment.unknown"
        assert result["status"]     == "pending"

    # ── disburse_b2c ──────────────────────────────────────────────────────

    def test_disburse_b2c_requires_initiator_config(self, provider):
        with pytest.raises(PaymentInitializationError, match="missing config"):
            provider.disburse_b2c(amount=500.00, phone="254712345678")

    def test_disburse_b2c_success(self, provider_with_initiator):
        token_resp = _daraja_token_resp()
        b2c_resp   = _mock_http_response({
            "ConversationID":           "conv-b2c-888",
            "OriginatorConversationID": "orig-b2c-888",
            "ResponseCode":             "0",
            "ResponseDescription":      "Accept the service request successfully.",
        })

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider_with_initiator._session, "post", return_value=b2c_resp):
            result = provider_with_initiator.disburse_b2c(
                amount=200.00, phone="254712345678", command_id="SalaryPayment",
            )

        assert result["status"]        == "pending"
        assert result["transaction_id"] == "conv-b2c-888"

    def test_disburse_b2c_normalises_phone(self, provider_with_initiator):
        token_resp = _daraja_token_resp()
        b2c_resp   = _mock_http_response({"ConversationID": "conv-xxx", "ResponseCode": "0"})

        with patch("requests.get", return_value=token_resp), \
             patch.object(provider_with_initiator._session, "post", return_value=b2c_resp) as mock_post:
            provider_with_initiator.disburse_b2c(amount=100.00, phone="0712345678")

        body = mock_post.call_args[1]["json"]
        assert body["PartyB"] == "254712345678"


# ===========================================================================
# CPayProvider
# ===========================================================================

class TestCPayProvider:
    """Tests for the real CPayProvider (Chaperone Payments API v1.1)."""

    # ── fixtures ──────────────────────────────────────────────────────────

    @pytest.fixture
    def cpay_config(self):
        return {
            "api_key":     "cpay_test_api_key",
            "api_secret":  "cpay_test_api_secret",
            "client_code": "CLIENT_TEST01",
            "base_url":    "https://cpay-uat-env.chaperone.co.ls:5100",
            "verify_ssl":  False,  # UAT uses a self-signed cert
        }

    @pytest.fixture
    def provider(self, cpay_config):
        return CPayProvider(cpay_config)

    @pytest.fixture
    def async_success_resp(self):
        return _mock_http_response({
            "statusCode":           "200",
            "description":          "Payment request created",
            "extTransactionId":     "EXT-TXN-001",
            "cPayTransactionId":    "CPAY_TXN_111",
            "paymentRequestStatus": "open",
            "additionalData":       "",
            "reasonCode":           "",
        })

    @pytest.fixture
    def status_processed_resp(self):
        return _mock_http_response({
            "statusCode":           "200",
            "description":          "Transaction processed",
            "extTransactionId":     "EXT-TXN-001",
            "cPayTransactionId":    "CPAY_TXN_111",
            "paymentRequestStatus": "processed",
            "reasonCode":           "",
        })

    # ── initialisation ────────────────────────────────────────────────────

    def test_initialization_sets_attributes(self, provider, cpay_config):
        assert provider.api_key     == cpay_config["api_key"]
        assert provider.api_secret  == cpay_config["api_secret"]
        assert provider.client_code == cpay_config["client_code"]
        assert provider.verify_ssl  is False

    def test_initialization_missing_api_key_raises(self, cpay_config):
        with pytest.raises(ValueError, match="api_key"):
            CPayProvider({**cpay_config, "api_key": ""})

    def test_initialization_missing_api_secret_raises(self, cpay_config):
        with pytest.raises(ValueError, match="api_secret"):
            CPayProvider({**cpay_config, "api_secret": ""})

    def test_initialization_missing_client_code_raises(self, cpay_config):
        """client_code is required in the real provider (was not in the old mock)."""
        with pytest.raises(ValueError, match="client_code"):
            CPayProvider({**cpay_config, "client_code": ""})

    def test_session_has_auth_header(self, provider, cpay_config):
        assert provider._session.headers["Authorization"] == cpay_config["api_key"]

    # ── _compute_checksum ─────────────────────────────────────────────────

    def test_checksum_initiation(self, provider):
        """Initiation checksum: HMAC-SHA256(ext_id + client_code + amount + msisdn)."""
        import hmac as _hmac, hashlib
        ext_id, amount, msisdn = "EXT-001", 50.0, "+26650123456"
        salt     = ext_id + provider.client_code + f"{amount:.2f}" + msisdn
        expected = _hmac.new(provider.api_secret.encode(), salt.encode(), hashlib.sha256).hexdigest()
        assert provider._compute_checksum(ext_id, amount, msisdn) == expected

    def test_checksum_confirmation_appends_otp(self, provider):
        """Confirmation checksum appends OTP to the salt."""
        import hmac as _hmac, hashlib
        ext_id, amount, msisdn, otp = "EXT-002", 100.0, "+26650123456", "654321"
        salt     = ext_id + provider.client_code + f"{amount:.2f}" + msisdn + otp
        expected = _hmac.new(provider.api_secret.encode(), salt.encode(), hashlib.sha256).hexdigest()
        assert provider._compute_checksum(ext_id, amount, msisdn, otp) == expected

    # ── initialize_payment ────────────────────────────────────────────────

    def test_initialize_async_success(self, provider, async_success_resp):
        """Default (async) mode returns pending status and correct transaction_id."""
        with patch.object(provider._session, "post", return_value=async_success_resp):
            result = provider.initialize_payment(
                amount=50.00,
                currency="LSL",
                customer_data={
                    "msisdn":             "+26650123456",
                    "ext_transaction_id": "EXT-TXN-001",
                },
            )

        assert result["transaction_id"]                              == "EXT-TXN-001"
        assert result["status"]                                      == "pending"
        assert result["payment_url"]                                 is None
        assert result["additional_data"]["payment_mode"]             == "async_ussd"
        assert result["additional_data"]["cpay_transaction_id"]      == "CPAY_TXN_111"

    def test_initialize_async_is_default_mode(self, provider, async_success_resp):
        """When no payment_mode is provided, async is used."""
        with patch.object(provider._session, "post", return_value=async_success_resp):
            result = provider.initialize_payment(
                amount=50.00,
                currency="LSL",
                customer_data={"msisdn": "+26650123456", "ext_transaction_id": "EXT-TXN-001"},
            )
        assert result["additional_data"]["payment_mode"] == "async_ussd"

    def test_initialize_otp_mode(self, provider):
        """OTP mode hits /payment endpoint and marks mode='otp' in response."""
        otp_resp = _mock_http_response({
            "statusCode":       "200",
            "description":      "Payment initiated, awaiting OTP",
            "extTransactionId": "EXT-OTP-001",
            "reasonCode":       "otpSend",
        })

        with patch.object(provider._session, "post", return_value=otp_resp):
            result = provider.initialize_payment(
                amount=75.00,
                currency="LSL",
                customer_data={
                    "msisdn":             "+26650123456",
                    "ext_transaction_id": "EXT-OTP-001",
                    "payment_mode":       "otp",
                },
            )

        assert result["status"]                            == "pending"
        assert result["additional_data"]["payment_mode"]   == "otp"
        assert result["additional_data"]["reason_code"]    == "otpSend"

    def test_initialize_missing_msisdn_raises(self, provider):
        with pytest.raises(PaymentInitializationError, match="msisdn"):
            provider.initialize_payment(
                amount=50.00, currency="LSL",
                customer_data={"ext_transaction_id": "EXT-NO-PHONE"},
            )

    def test_initialize_missing_ext_transaction_id_raises(self, provider):
        with pytest.raises(PaymentInitializationError, match="ext_transaction_id"):
            provider.initialize_payment(
                amount=50.00, currency="LSL",
                customer_data={"msisdn": "+26650123456"},
            )

    def test_initialize_unknown_mode_raises(self, provider):
        with pytest.raises(PaymentInitializationError, match="unknown payment_mode"):
            provider.initialize_payment(
                amount=50.00, currency="LSL",
                customer_data={
                    "msisdn":             "+26650123456",
                    "ext_transaction_id": "EXT-001",
                    "payment_mode":       "instant",
                },
            )

    def test_initialize_http_error_raises(self, provider):
        err_resp = _mock_http_response({"description": "Validation error"}, 400)
        with patch.object(provider._session, "post", return_value=err_resp):
            with pytest.raises(PaymentInitializationError):
                provider.initialize_payment(
                    amount=50.00, currency="LSL",
                    customer_data={"msisdn": "+26650123456", "ext_transaction_id": "EXT-ERR-001"},
                )

    def test_initialize_sends_valid_checksum(self, provider, async_success_resp):
        """The outgoing payload includes a 64-char HMAC-SHA256 checksum."""
        with patch.object(provider._session, "post", return_value=async_success_resp) as mock_post:
            provider.initialize_payment(
                amount=50.00, currency="LSL",
                customer_data={"msisdn": "+26650123456", "ext_transaction_id": "EXT-CHKSUM-01"},
            )

        body     = mock_post.call_args[1]["json"]
        checksum = body["transactionRequest"]["checksum"]
        assert checksum and len(checksum) == 64  # SHA-256 hex digest is always 64 chars

    def test_initialize_sends_client_code(self, provider, async_success_resp):
        with patch.object(provider._session, "post", return_value=async_success_resp) as mock_post:
            provider.initialize_payment(
                amount=50.00, currency="LSL",
                customer_data={"msisdn": "+26650123456", "ext_transaction_id": "EXT-CC-01"},
            )

        body = mock_post.call_args[1]["json"]
        assert body["transactionRequest"]["clientCode"] == provider.client_code

    # ── verify_payment ────────────────────────────────────────────────────

    def test_verify_payment_processed(self, provider, status_processed_resp):
        """'processed' paymentRequestStatus maps to 'completed'."""
        with patch.object(provider._session, "get", return_value=status_processed_resp):
            result = provider.verify_payment("EXT-TXN-001")

        assert result["status"]  == "completed"
        # /transaction-status does NOT echo amount or currency
        assert result["amount"]   is None
        assert result["currency"] is None
        assert result["additional_data"]["cpay_transaction_id"] == "CPAY_TXN_111"
        assert result["additional_data"]["cpay_status"]         == "processed"

    def test_verify_payment_open_is_pending(self, provider):
        resp = _mock_http_response({"paymentRequestStatus": "open"})
        with patch.object(provider._session, "get", return_value=resp):
            result = provider.verify_payment("EXT-OPEN")
        assert result["status"] == "pending"

    def test_verify_payment_denied_is_failed(self, provider):
        resp = _mock_http_response({"paymentRequestStatus": "denied"})
        with patch.object(provider._session, "get", return_value=resp):
            result = provider.verify_payment("EXT-DENIED")
        assert result["status"] == "failed"

    def test_verify_payment_reversed_is_refunded(self, provider):
        resp = _mock_http_response({"paymentRequestStatus": "reversed"})
        with patch.object(provider._session, "get", return_value=resp):
            result = provider.verify_payment("EXT-REVERSED")
        assert result["status"] == "refunded"

    def test_verify_payment_404_raises(self, provider):
        """HTTP 404 raises PaymentVerificationError."""
        not_found = _mock_http_response({"description": "Not found"}, 404)
        with patch.object(provider._session, "get", return_value=not_found):
            with pytest.raises(PaymentVerificationError, match="not found"):
                provider.verify_payment("EXT-MISSING")

    def test_verify_payment_network_error_raises(self, provider):
        with patch.object(provider._session, "get", side_effect=ConnectionError("timeout")):
            with pytest.raises(PaymentVerificationError, match="network error"):
                provider.verify_payment("EXT-NETFAIL")

    def test_verify_payment_uses_correct_query_param(self, provider, status_processed_resp):
        """verify_payment passes ext_transaction_id as the requestReference param."""
        with patch.object(provider._session, "get", return_value=status_processed_resp) as mock_get:
            provider.verify_payment("MY-EXT-REF-99")

        params = mock_get.call_args[1]["params"]
        assert params["requestReference"] == "MY-EXT-REF-99"

    # ── refund_payment ────────────────────────────────────────────────────

    def test_refund_always_raises_refund_error(self, provider):
        """CPay v1.1 has no programmatic refund endpoint – always raises."""
        with pytest.raises(RefundError, match="merchant portal"):
            provider.refund_payment("EXT-TXN-001", amount=50.00)

    def test_refund_error_message_contains_tx_reference(self, provider):
        tx_ref = "EXT-TXN-REF-XYZ"
        with pytest.raises(RefundError, match=tx_ref):
            provider.refund_payment(tx_ref)

    # ── verify_webhook_signature ──────────────────────────────────────────

    def test_verify_webhook_signature_always_returns_true(self, provider):
        """CPay push notifications carry no HMAC header -> always True."""
        assert provider.verify_webhook_signature(b'{"any": "payload"}', "any_sig") is True
        assert provider.verify_webhook_signature(b'{}', "")                        is True

    # ── handle_webhook ────────────────────────────────────────────────────

    def test_handle_webhook_processed(self, provider):
        """Flat 'processed' status payload -> completed."""
        payload = {
            "statusCode":           "0000",
            "description":          "Payment processed successfully",
            "extTransactionId":     "EXT-TXN-001",
            "cPayTransactionId":    "CPAY_TXN_111",
            "paymentRequestStatus": "processed",
            "additionalData":       "",
            "reasonCode":           "",
        }
        result = provider.handle_webhook(payload)

        assert result["transaction_id"]                             == "EXT-TXN-001"
        assert result["event_type"]                                 == "payment.completed"
        assert result["status"]                                     == "completed"
        assert result["additional_data"]["cpay_transaction_id"]     == "CPAY_TXN_111"

    def test_handle_webhook_denied(self, provider):
        payload = {"extTransactionId": "EXT-DENIED", "paymentRequestStatus": "denied", "reasonCode": ""}
        result  = provider.handle_webhook(payload)
        assert result["status"]     == "failed"
        assert result["event_type"] == "payment.failed"

    def test_handle_webhook_cancelled(self, provider):
        payload = {"extTransactionId": "EXT-CANCEL", "paymentRequestStatus": "canceled", "reasonCode": "canceled"}
        result  = provider.handle_webhook(payload)
        assert result["status"]     == "failed"
        assert result["event_type"] == "payment.cancelled"

    def test_handle_webhook_expired(self, provider):
        payload = {"extTransactionId": "EXT-EXPIRED", "paymentRequestStatus": "expired", "reasonCode": "expired"}
        result  = provider.handle_webhook(payload)
        assert result["status"]     == "failed"
        assert result["event_type"] == "payment.expired"

    def test_handle_webhook_reversed(self, provider):
        payload = {"extTransactionId": "EXT-REVERSED", "paymentRequestStatus": "reversed", "reasonCode": ""}
        result  = provider.handle_webhook(payload)
        assert result["status"]     == "refunded"
        assert result["event_type"] == "payment.reversed"

    def test_handle_webhook_open_is_pending(self, provider):
        payload = {"extTransactionId": "EXT-OPEN", "paymentRequestStatus": "open", "reasonCode": ""}
        result  = provider.handle_webhook(payload)
        assert result["status"]     == "pending"
        assert result["event_type"] == "payment.pending"

    def test_handle_webhook_old_nested_shape_no_longer_valid(self, provider):
        """The old mock used an event/data nested payload – confirm it no longer works."""
        old_shape = {
            "event": "payment.success",
            "data":  {"transaction_id": "OLD-TX-ID", "amount": 1000},
        }
        result = provider.handle_webhook(old_shape)
        # extTransactionId is absent -> empty string
        assert result["transaction_id"] == ""
        # paymentRequestStatus is absent -> pending
        assert result["status"] == "pending"

    # ── confirm_otp_payment ───────────────────────────────────────────────

    def test_confirm_otp_payment_success(self, provider):
        confirmed_resp = _mock_http_response({
            "statusCode":           "0000",
            "description":          "Payment processed successfully",
            "extTransactionId":     "EXT-OTP-001",
            "cPayTransactionId":    "CPAY_TXN_OTP",
            "paymentRequestStatus": "processed",
            "reasonCode":           "",
        })

        with patch.object(provider._session, "post", return_value=confirmed_resp):
            result = provider.confirm_otp_payment(
                ext_transaction_id="EXT-OTP-001",
                otp="123456",
                amount=75.00,
                msisdn="+26650123456",
            )

        assert result["status"]                                      == "completed"
        assert result["transaction_id"]                              == "EXT-OTP-001"
        assert result["additional_data"]["cpay_transaction_id"]      == "CPAY_TXN_OTP"

    # ── _map_status parametric coverage ──────────────────────────────────

    @pytest.mark.parametrize("cpay_status, expected", [
        ("processed",   "completed"),
        ("open",        "pending"),
        ("scheduled",   "pending"),
        ("denied",      "failed"),
        ("canceled",    "failed"),
        ("cancelled",   "failed"),
        ("expired",     "failed"),
        ("reversed",    "refunded"),
        ("0000",        "completed"),
        ("unknown_xyz", "pending"),   # unmapped -> pending fallback
    ])
    def test_map_status(self, cpay_status, expected):
        from app.providers.cpay_provider import _map_status
        assert _map_status(cpay_status) == expected

    def test_map_status_none_returns_pending(self):
        from app.providers.cpay_provider import _map_status
        assert _map_status(None) == "pending"


# ===========================================================================
# Stripe – UNCHANGED; StripeProvider was not modified
# ===========================================================================

class TestStripeProvider:
    """Tests for StripeProvider – identical to the original test suite."""

    @pytest.fixture
    def stripe_config(self):
        return {"api_key": "sk_test_123", "webhook_secret": "whsec_123"}

    @pytest.fixture
    def stripe_provider(self, stripe_config):
        from app.providers.stripe_provider import StripeProvider
        return StripeProvider(stripe_config)

    def test_stripe_initialization(self, stripe_provider):
        assert stripe_provider.api_key        == "sk_test_123"
        assert stripe_provider.webhook_secret == "whsec_123"

    @patch("stripe.PaymentIntent.create")
    @patch("stripe.Customer.create")
    @patch("stripe.Customer.list")
    def test_initialize_payment_new_customer(
        self, mock_list, mock_create_customer, mock_create_pi, stripe_provider
    ):
        mock_list.return_value.data = []

        mock_customer    = Mock()
        mock_customer.id = "cus_123"
        mock_create_customer.return_value = mock_customer

        mock_pi                      = Mock()
        mock_pi.id                   = "pi_123"
        mock_pi.client_secret        = "pi_123_secret"
        mock_pi.status               = "requires_payment_method"
        mock_pi.amount               = 10000
        mock_pi.currency             = "usd"
        mock_pi.payment_method_types = ["card"]
        mock_create_pi.return_value  = mock_pi

        result = stripe_provider.initialize_payment(
            amount=100.00,
            currency="USD",
            customer_data={"email": "test@example.com", "name": "Test User"},
        )

        assert result["transaction_id"] == "pi_123"
        assert result["client_secret"]  == "pi_123_secret"
        assert result["status"]         == "pending"

    @patch("stripe.PaymentIntent.retrieve")
    def test_verify_payment(self, mock_retrieve, stripe_provider):
        mock_pi                = Mock()
        mock_pi.id             = "pi_123"
        mock_pi.status         = "succeeded"
        mock_pi.amount         = 10000
        mock_pi.currency       = "usd"
        mock_pi.payment_method = "pm_123"
        mock_pi.receipt_email  = "test@example.com"
        mock_pi.charges.data   = []
        mock_retrieve.return_value = mock_pi

        result = stripe_provider.verify_payment("pi_123")

        assert result["status"]   == "completed"
        assert result["amount"]   == 100.00
        assert result["currency"] == "USD"

    @patch("stripe.Refund.create")
    @patch("stripe.PaymentIntent.retrieve")
    def test_refund_payment(self, mock_retrieve_pi, mock_create_refund, stripe_provider):
        mock_charge    = Mock()
        mock_charge.id = "ch_123"
        mock_pi        = Mock()
        mock_pi.charges.data = [mock_charge]
        mock_retrieve_pi.return_value = mock_pi

        mock_refund                = Mock()
        mock_refund.id             = "re_123"
        mock_refund.status         = "succeeded"
        mock_refund.amount         = 10000
        mock_refund.currency       = "usd"
        mock_refund.reason         = "requested_by_customer"
        mock_refund.charge         = "ch_123"
        mock_refund.payment_intent = "pi_123"
        mock_refund.created        = 1234567890
        mock_create_refund.return_value = mock_refund

        result = stripe_provider.refund_payment("pi_123", amount=100.00)

        assert result["refund_id"] == "re_123"
        assert result["status"]    == "succeeded"
        assert result["amount"]    == 100.00