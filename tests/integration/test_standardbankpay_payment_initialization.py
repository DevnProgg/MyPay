import pytest
import requests
import uuid

# Configuration for the target API
BASE_URL = "http://localhost:5050"
API_KEY = "sbp_test_sk_8f3920"
CLIENT_ID = "sbp-client-001"


@pytest.mark.integration
def test_initialize_payment_to_live_server():
    """
    Integration test to initialize a payment with a live server.

    This test requires the provider's Flask API to be running at BASE_URL.
    """
    url = f"{BASE_URL}/api/v1/payments/initiate"
    request_id = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-SBP-Client-Id": CLIENT_ID,
        "X-SBP-Request-Id": request_id,
        "Content-Type": "application/json",
    }

    payload = {
        "amount_cents": 5000,  # 50.00
        "currency_code": "ZAR",
        "payer": {"msisdn": "+27821234567"},
        "callback_url": "https://my-shop.com/payment/callback",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # Assertions for a successful response
        assert response.status_code == 201
        data = response.json()
        assert "sbp_txn_ref" in data
        assert "approval_url" in data
        assert data["processing_state"] == "AWAITING_CUSTOMER"

    except requests.exceptions.RequestException as e:
        pytest.fail(
            f"Failed to connect to the API at {url}. "
            f"Please ensure the server is running and accessible. Error: {e}"
        )


@pytest.mark.integration
def test_initialize_payment_exceeds_limit():
    """
    Integration test for a payment that should be rejected for exceeding the limit.
    """
    url = f"{BASE_URL}/api/v1/payments/initiate"
    request_id = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-SBP-Client-Id": CLIENT_ID,
        "X-SBP-Request-Id": request_id,
        "Content-Type": "application/json",
    }

    payload = {
        "amount_cents": 150_000,  # 1500.00, which is over the 100_000 limit
        "currency": "ZAR",
        "customer": {"msisdn": "+27821234567"},
        "callback_url": "https://my-shop.com/payment/callback",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)

        # Assertions for a rejected transaction
        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Amount exceeds daily limit"

    except requests.exceptions.RequestException as e:
        pytest.fail(
            f"Failed to connect to the API at {url}. "
            f"Please ensure the server is running and accessible. Error: {e}"
        )
