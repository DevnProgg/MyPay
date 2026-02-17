# MyPay In-Depth Code Documentation

This document provides a detailed walkthrough of the MyPay application's source code, architecture, and key components. It's intended for developers who will be actively working on the codebase.

## 1. Architectural Overview

The MyPay application is built using a **layered architecture** that separates concerns, enhances modularity, and simplifies maintenance. The layers are organized as follows:

1.  **API Layer (`app/api`)**: The outermost layer, responsible for handling incoming HTTP requests, validating request data, and serializing responses. It acts as the entry point for all external interactions.
2.  **Service Layer (`app/services`)**: This is the core business logic layer. It orchestrates complex operations, coordinates between different parts of the application (like models and providers), and ensures that business rules are enforced.
3.  **Provider Layer (`app/providers`)**: A key abstraction that contains the logic for interacting with external payment gateways. It consists of a base interface and concrete implementations for each provider, making the system highly extensible.
4.  **Data Layer (`app/models`)**: Defines the structure of the application's data using SQLAlchemy models. This layer is responsible for all database interactions.
5.  **Shared Components (`app/utils`, `app/extensions`)**: Cross-cutting concerns like configuration, logging, database connections, and other extensions are managed here.

---

## 2. Data Flow: Tracing a Payment Initialization

To understand how the layers interact, let's trace a typical `initialize_payment` request through the system.

1.  **HTTP Request Received**: A client sends a `POST` request to the `/initialize` endpoint.

2.  **API Layer (`app/api/payments.py`)**:
    - The `initialize_payment` function in `payments_bp` receives the request.
    - The `@idempotent` decorator intercepts the request to ensure it hasn't been processed before, using the `Idempotency-Key` header.
    - The `InitializePaymentSchema` (from `app/schemas`) is used to validate the JSON body of the request. If validation fails, a `400 Bad Request` is returned immediately.
    - If validation is successful, the function calls `PaymentService.initialize_payment()`, passing the validated data.

3.  **Service Layer (`app/services/payment_service.py`)**:
    - The `initialize_payment` static method in `PaymentService` takes over.
    - It first checks if a `Transaction` with the same `idempotency_key` already exists. If so, it returns the existing transaction without processing a new one.
    - A new `Transaction` object is created in the database with a `PENDING` status. This provides a persistent record of the request before any external calls are made.
    - An `AuditService.log_event()` call records that the payment was initiated.
    - A WebSocket event is emitted via `emit_transaction_update()` to notify any connected clients (like a dashboard) of the new transaction.
    - The service then calls `get_provider(provider_name)` to dynamically load the correct provider module (e.g., `CPayProvider`).
    - It calls the `initialize_payment()` method on the instantiated provider object.

4.  **Provider Layer (`app/providers/cpay_provider.py`)**:
    - The `initialize_payment` method within the `CPayProvider` class builds the request payload specific to the CPay API.
    - It calculates a required `checksum` for request signing.
    - It uses the `requests` library to send a `POST` request to the external CPay API endpoint.
    - It handles the response from CPay, checking for errors. If successful, it returns a dictionary containing the `provider_transaction_id` and other relevant data.

5.  **Service Layer (Resumed)**:
    - The `PaymentService` receives the result from the provider.
    - It updates the `Transaction` record in the database with the `provider_transaction_id`, the full provider response, and changes the status to `PROCESSING`.
    - It logs another audit event (`payment.processing`) and emits another WebSocket event to reflect the status change.
    - If any exception occurred during the provider call, it catches the error, updates the transaction status to `FAILED`, logs the error, and re-raises the exception.

6.  **API Layer (Resumed)**:
    - The `payments_bp` function receives the final `Transaction` object from the service.
    - It uses the `TransactionSchema` to serialize the object into a clean JSON format.
    - It wraps the serialized data in a standard response envelope (`{"success": true, "data": ...}`) and returns it to the client with a `201 Created` status code.

---

## 3. Core Components Deep Dive

### `app/config.py`
-   **Purpose**: Manages application configuration for different environments (Development, Production, Testing).
-   **Mechanism**: It uses a class-based approach. The base `Config` class loads values from environment variables (`.env` file) using `os.getenv()`. Child classes like `DevelopmentConfig` can override these for specific needs.
-   **Key Variables**: `SECRET_KEY`, `SQLALCHEMY_DATABASE_URI`, `REDIS_URL`, and provider-specific keys like `CPAY_API_KEY`.

### `app/models/transaction.py`
-   **Purpose**: Defines the central data entity for the entire application.
-   **Structure**:
    -   It's a SQLAlchemy `db.Model`.
    -   `id`: Primary key, a UUID.
    -   `idempotency_key`: Crucial for preventing duplicate requests.
    -   `provider` & `provider_transaction_id`: Links the transaction to the external payment gateway's records.
    -   `status`: A string enum (`TransactionStatus`) that represents the lifecycle of the transaction (`PENDING`, `PROCESSING`, `COMPLETED`, etc.).
    -   `provider_response` & `metadata`: `JSONB` columns for storing unstructured data from providers or clients.
    -   **Relationships**: It has relationships to `AuditLog` and `WebhookEvent`, allowing for a detailed history of each transaction to be stored.

### `app/providers/base.py`
-   **Purpose**: This file is the cornerstone of the aggregator's extensible design.
-   **Structure**:
    -   It defines an abstract base class `PaymentProvider` using Python's `abc` module.
    -   It declares abstract methods that every concrete provider **must** implement:
        -   `initialize_payment()`: To start a payment.
        -   `verify_payment()`: To check the status of a payment.
        -   `refund_payment()`: To process a refund.
        -   `verify_webhook_signature()` & `handle_webhook()`: To securely process asynchronous updates from providers.
    -   This contract ensures that the `PaymentService` can interact with any provider through a consistent interface, without needing to know the implementation details of each one.

### `app/services/payment_service.py`
-   **Purpose**: The brain of the application, containing all business logic related to payments.
-   **Key Responsibilities**:
    -   **State Management**: It's the single source of truth for creating and transitioning the state of a `Transaction` (e.g., from `PENDING` to `PROCESSING`).
    -   **Orchestration**: It coordinates interactions between the API controllers, the `Transaction` model, and the correct `PaymentProvider`.
    -   **Error Handling**: It contains `try...except` blocks to gracefully handle failures from provider APIs, ensuring the transaction status is updated to `FAILED`.
    -   **Side Effects**: It triggers side effects like audit logging (`AuditService`) and real-time updates (`emit_transaction_update`).

### `app/api/payments.py`
-   **Purpose**: To expose the payment functionality via a RESTful API.
-   **Structure**:
    -   It uses a Flask `Blueprint` (`payments_bp`) to group related routes.
    -   Each route function is responsible for a single API action (`initialize`, `get`, `verify`, `refund`).
    -   **Validation**: It strictly relies on Marshmallow schemas (`InitializePaymentSchema`, `RefundPaymentSchema`) to validate incoming data, keeping the controller logic clean.
    -   **Delegation**: The route handlers contain minimal logic. Their primary job is to call the appropriate method on `PaymentService` and format the result as a JSON response.
