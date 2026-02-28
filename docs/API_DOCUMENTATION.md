# MyPay API Documentation

This document describes the REST API for the MyPay Payment Gateway Aggregator.

## Authentication

The API uses two types of authentication:

### 1. API Key (Merchant API)
Most merchant-facing endpoints require an API Key.
- **Header:** `X-API-Key: your_api_key_here`

### 2. JWT (Admin API)
Administrative endpoints require a JSON Web Token (JWT).
- **Header:** `Authorization: Bearer <your_jwt_token>`
- Obtain a token via the `/api/v1/auth/admin/login` endpoint.

---

## Idempotency

To prevent duplicate transactions due to network retries, some POST endpoints support idempotency.
- **Header:** `Idempotency-Key: <unique_string>`
- If a request with the same `Idempotency-Key` is received within 24 hours, the original response is returned without re-processing.

---

## Payment Endpoints

### Initialize Payment
`POST /api/v1/payments/initialize`

Initializes a new payment transaction with a specific provider.

**Headers:**
- `X-API-Key`: Required
- `Idempotency-Key`: Highly Recommended

**Request Body:**
```json
{
    "provider": "mpesa",
    "amount": 1000.00,
    "currency": "LSL",
    "customer": {
        "phone": "+26657502734",
        "email": "customer@example.com",
        "name": "John Doe"
    },
    "metadata": {
        "order_id": "ORD-12345"
    }
}
```

**Response (201 Created):**
```json
{
    "success": true,
    "data": {
        "id": "uuid-v4-transaction-id",
        "status": "pending",
        "amount": 1000.0,
        "currency": "LSL",
        "provider": "mpesa",
        "created_at": "2024-02-26T10:00:00Z"
    }
}
```

### Get Payment Details
`GET /api/v1/payments/<uuid:transaction_id>`

Retrieves the current status and details of a transaction.

**Response (200 OK):**
```json
{
    "success": true,
    "data": {
        "id": "...",
        "status": "completed",
        "amount": 1000.0,
        ...
    }
}
```

### Verify Payment
`POST /api/v1/payments/<uuid:transaction_id>/verify`

Force a real-time status check with the payment provider. Useful if a webhook hasn't been received yet.

### List Payments
`GET /api/v1/payments/payments`

**Query Parameters:**
- `provider`: Filter by provider
- `status`: Filter by status (pending, completed, failed)
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 20)

---

## Webhook Endpoints

### Receive Webhook
`POST /api/v1/webhooks/<provider>`

Endpoint for payment providers to send asynchronous notifications.
- **Providers supported:** `Depends on provider adapters added to the registry`
- **Security:** Varies by provider (e.g., `X-CPay-Signature` header for CPay).

---

## Admin Endpoints

### Get Statistics
`GET /api/v1/admin/statistics`

Returns an overview of transaction volumes, success rates, and provider distribution.

### List Providers
`GET /api/v1/admin/providers`

Lists all available and configured payment providers.

### Audit Logs
`GET /api/v1/admin/audit-logs`

Query detailed logs of all system events.
