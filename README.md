# MyPay - Payment Gateway Aggregator

MyPay is a flexible and scalable payment gateway aggregator written in Python. It provides a unified API to interact with multiple payment providers, simplifying payment processing and webhook handling.

## Overview

This application serves as a central hub for payment operations. Instead of integrating with multiple provider-specific APIs, a client application can integrate with MyPay's simple REST API. MyPay then routes the requests to the appropriate payment provider (e.g., M-Pesa, C-Pay) and standardizes the responses.

## Features

- **Multi-Provider Support:** Easily extensible to support various payment providers. Comes with M-Pesa and C-Pay pre-integrated.
- **Unified REST API:** A single API for initiating, querying, and managing payments.
- **Webhook Handling:** A robust system for receiving and processing asynchronous notifications from providers.
- **Idempotency:** Ensures that repeated API requests do not result in duplicate transactions.
- **Audit Logging:** Keeps a detailed log of all significant events for traceability and debugging.
- **Containerized:** Ready to be deployed and scaled using Docker and Docker Compose.
- **Real-time Updates:** Uses WebSockets to push real-time event updates to connected clients.

## Getting Started

The recommended way to run the project is by using Docker and Docker Compose, which handles the setup of the application, database, and Redis cache.

### Prerequisites

- Git
- Docker
- Docker Compose

### Installation & Running

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd MyPay
    ```

2.  **Configuration:**
    The project uses a `.env` file for configuration. While a default configuration is provided in `docker-compose.yml` for development, you can create a `.env` file to override settings, especially for production.

3.  **Build and run the application:**
    ```bash
    docker-compose up --build -d
    ```
    This command will build the Docker image, start the application container along with PostgreSQL and Redis, and run database migrations. The application will be accessible at `http://localhost:5000`.

### Running Tests

The project uses `pytest` for testing. To run the test suite, you can execute the following command to run the tests inside the Docker container:

```bash
docker-compose exec app pytest
```

## Project Structure

- **/app:** Main application source code.
- **/app/api:** Contains all the API endpoint definitions (payments, webhooks, etc.).
- **/app/providers:** Houses the specific logic for each integrated payment provider.
- **/app/services:** Contains the core business logic.
- **/app/models:** Defines the SQLAlchemy database models.
- **/tests:** Contains unit and integration tests.
- **/docs:** Includes project documentation like the developer guide.

## Documentation

For more detailed information on the architecture, API endpoints, and developer guidelines, please refer to the documents in the `/docs` directory.
