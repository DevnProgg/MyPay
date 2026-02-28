# MyPay - Payment Gateway Aggregator

MyPay is a flexible and scalable payment gateway aggregator written in Python. It provides a unified API to interact with multiple payment providers, simplifying payment processing and webhook handling.

## Overview

This application serves as a central hub for payment operations. Instead of integrating with multiple provider-specific APIs, a client application can integrate with MyPay's simple REST API. MyPay then routes the requests to the appropriate payment provider (e.g., M-Pesa, C-Pay) and standardizes the responses.

## Features

- **Multi-Provider Support:** Architected to support various payment providers. Currently integrated with **Standard Bank Pay**.
- **Unified REST API:** A single API for initiating, querying, and managing payments.
- **Webhook Handling:** Robust system for receiving and processing asynchronous notifications with signature verification.
- **Idempotency:** Ensures that repeated API requests do not result in duplicate transactions using `Idempotency-Key` headers.
- **Audit Logging:** Detailed logs of all significant events for traceability and debugging.
- **Containerized:** Ready to be deployed and scaled using Docker and Docker Compose.
- **Background Processing:** Uses Celery and Redis for asynchronous task execution (webhooks, reconciliation).

## Getting Started

### Prerequisites

- Git
- Docker and Docker Compose
- Python 3.12+ (if running without Docker)

### Installation & Running

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd MyPay
    ```

2.  **Configuration:**
    The project uses environment variables. For Docker, defaults are set in `docker-compose.yml`. For local development, create a `.env` file in the root:
    ```env
    SECRET_KEY=your-secret-key
    JWT_SECRET_KEY=your-jwt-secret
    DATABASE_URI=your-database-url
    REDIS_HOST=redis
    REDIS_PORT=6379
    ```

3.  **Build and run with Docker:**
    ```bash
    docker-compose up --build -d
    ```
    The application will be accessible at `http://localhost:5000`.

### Running Tests

Execute tests within the Docker environment:
```bash
docker-compose exec app pytest
```

## Project Structure

- **`/app`**: Core application logic.
    - **`/api`**: API blueprints and endpoint definitions.
    - **`/models`**: SQLAlchemy database models.
    - **`/providers`**: Individual payment provider implementations.
    - **`/services`**: Business logic layer (Payment, Auth, Webhooks).
    - **`/utils`**: Helper functions (Encryption, Logger, Decorators).
- **`/docs`**: Project documentation and architecture diagrams.
- **`/tests`**: Unit and integration test suites.
- **`/logs`**: Application log files.

## Documentation

Comprehensive documentation is available in the `/docs` directory:

-   [**API Documentation**](./docs/API_DOCUMENTATION.md): Detailed information on REST endpoints, authentication, and idempotency.
-   [**Developer Guide**](./docs/DEVELOPER_GUIDE.md): Architecture overview, guide for adding new providers, and development workflow.
-   [**Architecture Diagrams**](./docs/architecture.jpg): Visual representation of the system architecture.
-   [**Database Schema**](./docs/EER.jpg): Entity Relationship Diagram of the gateway.
