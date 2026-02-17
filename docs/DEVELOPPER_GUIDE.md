# MyPay Developer Onboarding Guide

Welcome to the MyPay project! This guide is designed to help you get your development environment set up and to understand the project structure so you can start contributing quickly.

## 1. Project Overview

MyPay is a payment gateway aggregator. It provides a unified API for processing payments through various third-party providers (like CPay and M-Pesa). The core goal is to abstract the complexities of individual payment gateways behind a simple, consistent interface.

## 2. Getting Started: Setup

You can run the project using either Docker (recommended for simplicity) or a local Python environment.

### Prerequisites

- Python 3.9+
- Docker and Docker Compose

### Option A: Docker Setup (Recommended)

This is the fastest way to get the application and its dependencies running.

1.  **Environment Configuration:**
    The application uses a `.env` file for configuration. Start by copying the example file (if one existed, otherwise create a new one):

    ```bash
    cp .env.example .env
    ```

    Now, open the `.env` file and fill in the necessary configuration details, such as database credentials and API keys for payment providers.

2.  **Build and Run the Containers:**
    Use Docker Compose to build the images and start the services.

    ```bash
    docker-compose up --build
    ```

    The application should now be running and accessible at `http://localhost:5000`.

### Option B: Local Python Environment

If you prefer not to use Docker, you can set up a local environment.

1.  **Create and Activate a Virtual Environment:**

    ```bash
    # For macOS/Linux
    python3 -m venv .venv
    source .venv/bin/activate

    # For Windows
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

2.  **Install Dependencies:**
    Install all required Python packages from the `requirements.txt` file.

    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment:**
    Create a `.env` file as described in the Docker setup.

4.  **Run the Application:**
    With your environment configured, you can run the Flask application.

    ```bash
    flask run
    ```

    The application will be available at `http://localhost:5000`.

## 3. Project Structure

The project follows a standard Flask application structure. Here's a breakdown of the key directories:

-   **/app**: The main application module.
    -   **/api**: Defines the public-facing API endpoints (e.g., `/payments`, `/webhooks`).
    -   **/models**: Contains the database models (e.g., `Transaction`, `ProviderConfig`).
    -   **/providers**: This is the core of the aggregator.
        -   `base.py`: Defines the abstract `BaseProvider` class that all providers must inherit from.
        -   `cpay_provider.py`, `mpesa_provider.py`: Implementations for specific payment gateways.
    -   **/schemas**: Defines serialization and validation schemas for API requests and responses.
    -   **/services**: Contains the business logic that orchestrates operations (e.g., `PaymentService` deciding which provider to use).
    -   **/utils**: Shared utilities, decorators, and helper functions.
    -   `config.py`: Loads configuration from environment variables.
-   **/tests**: Contains all the tests for the application.
    -   **/unit**: Unit tests for individual components.
    -   **/integration**: Integration tests for complete workflows.
-   **/migrations**: Database migration scripts (if using Flask-Migrate).
-   `app.py`: The entry point for the Flask application.
-   `requirements.txt`: Python package dependencies.
-   `Dockerfile`, `docker-compose.yml`: Docker configuration files.

## 4. Running Tests

The project uses `pytest` for testing. To run the entire test suite, execute the following command in your terminal:

```bash
pytest
```

This command will automatically discover and run all tests in the `tests/` directory.

## 5. How to Add a New Payment Provider

Adding a new provider is a common task. Here’s the typical workflow:

1.  **Create the Provider Module:**
    Add a new file in `app/providers/`, for example, `app/providers/new_provider.py`.

2.  **Implement the Provider Class:**
    Inside the new file, create a class that inherits from `BaseProvider` (from `app.providers.base`). You will need to implement all the abstract methods defined in the base class, such as `charge`, `refund`, and `get_status`.

    ```python
    # app/providers/new_provider.py
    from .base import BaseProvider

    class NewProvider(BaseProvider):
        def charge(self, amount: int, currency: str, **kwargs) -> dict:
            # Logic to call the new provider's API for a charge
            pass

        def refund(self, transaction_id: str, amount: int, **kwargs) -> dict:
            # Logic for refunds
            pass

        # ... implement other required methods
    ```

3.  **Add Configuration:**
    Add any required API keys, secrets, or endpoint URLs for the new provider to your `.env` file.

    ```
    NEW_PROVIDER_API_KEY=your_key
    NEW_PROVIDER_API_SECRET=your_secret
    ```

    Make sure to load these variables in `app/config.py`.

4.  **Register the Provider:**
    Update the `PaymentService` (in `app/services/payment_service.py`) to make it aware of the new provider. This usually involves adding it to a dictionary or a factory function that selects the provider based on the request.

5.  **Write Tests:**
    Add unit tests for your new provider in the `tests/unit/` directory to ensure it functions correctly.
