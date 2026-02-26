# MyPay Developer Guide

This guide is intended for developers who wish to contribute to the MyPay project or integrate it into their own environment.

## Architecture Overview

MyPay is built using a clean architecture approach, separating the API layer, business logic (services), and provider-specific integrations.

- **API Layer (`app/api`):** Defines REST endpoints and handles request/response formatting.
- **Service Layer (`app/services`):** Contains the core business logic, such as transaction management, idempotency, and audit logging.
- **Provider Layer (`app/providers`):** Implements the logic for communicating with external payment providers.
- **Models (`app/models`):** Defines the database schema using SQLAlchemy.

## Local Development Setup

### 1. Prerequisites
- Python 3.12+
- Docker and Docker Compose (recommended)
- PostgreSQL (if running locally)
- Redis (if running locally)

### 2. Manual Setup (Without Docker)
1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd MyPay
    ```
2.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure environment variables:**
    Create a `.env` file based on the settings in `docker-compose.yml`.
5.  **Run migrations:**
    ```bash
    flask db upgrade
    ```
6.  **Start the application:**
    ```bash
    python app.py
    ```

## Configuration

The application is configured using environment variables. These can be set in a `.env` file in the project root.

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for session security | `dev-secret-key` |
| `JWT_SECRET_KEY` | Secret key for JWT token signing | `dev-jwt-secret` |
| `DATABASE_URI` | PostgreSQL connection string | `postgresql://...` |
| `REDIS_HOST` | Hostname for Redis | `localhost` |
| `REDIS_PORT` | Port for Redis | `6379` |
| `REDIS_DB` | Redis database number | `0` |

## Adding a New Payment Provider

To add a new provider (e.g., PayPal), follow these steps:

1.  **Create a new file** in `app/providers/`: `app/providers/paypal_provider.py`.
2.  **Inherit from `PaymentProvider`** base class and implement the abstract methods:
    - `initialize_payment`: Call the provider's API to start a transaction.
    - `verify_payment`: Check the status of a transaction on the provider's side.
    - `verify_webhook_signature`: Security check for incoming webhooks.
    - `handle_webhook`: Parse and process the webhook payload.
3.  **Register the provider** in `app/providers/__init__.py`.

Example:
```python
from app.providers.base import PaymentProvider

class PayPalProvider(PaymentProvider):
    def initialize_payment(self, amount, currency, customer_data, metadata=None):
        # Implementation...
        pass
    # ... other methods ...
```

## Testing

The project uses `pytest` for testing.

- **Unit Tests:** `pytest tests/unit`
- **Integration Tests:** `pytest tests/integration`
- **Run all tests with coverage:** `pytest --cov=app tests/`

## Background Tasks

MyPay uses **Celery** for background tasks like:
- Processing webhooks asynchronously.
- Retrying failed webhook deliveries.
- Periodic transaction reconciliation.

To run the Celery worker:
```bash
celery -A app.extensions.celery worker --loglevel=info
```

To run the Celery beat (for scheduled tasks):
```bash
celery -A app.extensions.celery beat --loglevel=info
```

## Database Migrations

When you modify the models in `app/models/`, you need to generate and apply a migration:

1.  **Generate migration:**
    ```bash
    flask db migrate -m "Description of change"
    ```
2.  **Apply migration:**
    ```bash
    flask db upgrade
    ```
