import pytest
from unittest.mock import patch, Mock
from app.providers.standard_bank_pay_provider import StandardBankPayProvider, PaymentInitializationError

class TestStandardBankPayProvider:
    """Unit tests for the StandardBankPayProvider"""

    @pytest.fixture
    def provider(self):
        """Fixture for a StandardBankPayProvider instance"""
        config = {
            "base_url": "http://127.0.0.1:5000/api/v1",
            "api_key": "sbp_test_sk_8f3920",
            "client_id": "sbp-client-001",
        }
        return StandardBankPayProvider(config)

    @patch('requests.post')
    def test_initialize_payment_success(self, mock_post, provider):
        """Test successful payment initialization"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sbp_txn_ref": "txn_12345",
            "processing_state": "AWAITING_CUSTOMER",
            "approval_url": "http://127.0.0.1:5050/payments/initiate",
            "expires_in_seconds": 300,
            "meta": {
                "risk_score": 0.1
            }
        }
        mock_post.return_value = mock_response

        result = provider.initialize_payment(
            amount=100.0,
            currency="ZAR",
            customer_data={"msisdn": "+27820000000"},
            metadata={"request_id": "req_abc123"}
        )

        assert result["transaction_id"] == "txn_12345"
        assert result["status"] == "pending"
        assert result["payment_url"] == "http://localhost:5050/__simulate__/webhook/txn_12345"
        assert result["additional_data"]["expires_in"] == 300

        mock_post.assert_called_once_with(
            f"{provider.base_url}/api/v1/payments/initiate",
            json={
                "amount_cents": 10000,
                "currency": "ZAR",
                "customer": {"msisdn": "+27820000000"},
                "callback_url": None,
            },
            headers=provider._headers("req_abc123"),
            timeout=provider.timeout,
        )

    @patch('requests.post')
    def test_initialize_payment_api_error(self, mock_post, provider):
        """Test handling of API error during payment initialization"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid input"
        mock_post.return_value = mock_response

        with pytest.raises(PaymentInitializationError, match="Invalid input"):
            provider.initialize_payment(
                amount=100.0,
                currency="ZAR",
                customer_data={"msisdn": "+27820000000"},
                metadata={"request_id": "req_abc123"}
            )

    def test_initialize_payment_missing_request_id(self, provider):
        """Test that a missing request_id raises an error"""
        with pytest.raises(PaymentInitializationError, match="Missing request_id"):
            provider.initialize_payment(
                amount=100.0,
                currency="ZAR",
                customer_data={"msisdn": "+27820000000"},
                metadata={}
            )
