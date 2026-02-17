# Payment Gateway Prototype - Project Specifications

## Executive Summary

A production-ready payment gateway prototype built with Python Flask that provides a unified interface for integrating multiple payment providers (M-Pesa, Visa, CPay, etc.) with a "plug and play" architecture.

**Timeline:** 4 Days  
**Tech Stack:** Python Flask, PostgreSQL, Redis, WebSockets  
**Delivery Model:** Prototype with production-grade architecture

---

## Project Objectives

1. Create a unified payment gateway API that abstracts multiple payment providers
2. Implement "plug and play" architecture for easy payment provider integration
3. Build production-grade features: idempotency, auditability, webhooks, real-time notifications
4. Deliver clean, documented, and testable code
5. Provide comprehensive API documentation

---

## Deliverables

### 1. Core Application (Days 1-2)
- ✅ Flask application with modular architecture
- ✅ RESTful API endpoints for payment operations
- ✅ Database models and migrations (SQLAlchemy)
- ✅ Redis integration for caching and idempotency
- ✅ Environment-based configuration management

### 2. Payment Provider Integration Layer (Day 2)
- ✅ Abstract payment provider interface
- ✅ Provider registry/factory pattern
- ✅ Sample integrations:
  - M-Pesa (STK Push, B2C, C2B)
  - Visa/Card Processing (Stripe/PayStack as example)
  - CPay (mock implementation showing integration pattern)
- ✅ Provider configuration management

### 3. Production-Grade Features (Day 3)
- ✅ **Idempotency**: Request deduplication using idempotency keys
- ✅ **Auditability**: Complete audit trail for all transactions
- ✅ **Webhooks**: 
  - Webhook receiver endpoints
  - Webhook signature verification
  - Retry mechanism with exponential backoff
- ✅ **WebSockets**: Real-time payment status updates
- ✅ **Error Handling**: Comprehensive error handling and logging
- ✅ **Rate Limiting**: API rate limiting protection

### 4. Documentation & Testing (Day 4)
- ✅ API documentation (OpenAPI/Swagger)
- ✅ Unit tests (core business logic)
- ✅ Integration tests (payment flows)
- ✅ Developer guide and setup instructions
- ✅ Postman collection for API testing
- ✅ Docker containerization

### 5. Additional Components
- ✅ Admin dashboard (basic) for transaction monitoring
- ✅ Health check and monitoring endpoints
- ✅ Database migration scripts
- ✅ Environment setup scripts

---

## System Architecture

### High-Level Architecture

```
┌─────────────────┐
│   Client Apps   │
│  (Web/Mobile)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         API Gateway (Flask)             │
│  ┌──────────────────────────────────┐  │
│  │   Route Handlers & Validators    │  │
│  └──────────────┬───────────────────┘  │
│                 │                       │
│  ┌──────────────▼───────────────────┐  │
│  │     Payment Service Layer        │  │
│  │  • Idempotency Middleware        │  │
│  │  • Transaction Management        │  │
│  │  • Audit Logger                  │  │
│  └──────────────┬───────────────────┘  │
│                 │                       │
│  ┌──────────────▼───────────────────┐  │
│  │   Provider Abstraction Layer     │  │
│  │  ┌────────────────────────────┐  │  │
│  │  │  Provider Factory/Registry │  │  │
│  │  └─────────┬──────────────────┘  │  │
│  │            │                      │  │
│  │  ┌─────────▼──────────┐          │  │
│  │  │  Provider Adapters │          │  │
│  │  │  • M-Pesa          │          │  │
│  │  │  • Visa/Cards      │          │  │
│  │  │  • CPay            │          │  │
│  │  └────────────────────┘          │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
         │                 │
         ▼                 ▼
┌─────────────────┐ ┌─────────────────┐
│   PostgreSQL    │ │      Redis      │
│  • Transactions │ │  • Idempotency  │
│  • Audit Logs   │ │  • Cache        │
│  • Users        │ │  • Sessions     │
└─────────────────┘ └─────────────────┘

┌─────────────────────────────────────────┐
│        External Components              │
│  ┌──────────────┐  ┌─────────────────┐ │
│  │   Webhook    │  │   WebSocket     │ │
│  │  Listeners   │  │   Server        │ │
│  └──────────────┘  └─────────────────┘ │
└─────────────────────────────────────────┘
```

### Database Schema

#### Core Tables

**transactions**
- `id` (UUID, PK)
- `idempotency_key` (String, Unique, Indexed)
- `provider` (String)
- `amount` (Decimal)
- `currency` (String)
- `status` (Enum: pending, processing, completed, failed, refunded)
- `customer_id` (String)
- `payment_method` (String)
- `metadata` (JSONB)
- `provider_transaction_id` (String)
- `provider_response` (JSONB)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)

**audit_logs**
- `id` (UUID, PK)
- `transaction_id` (UUID, FK)
- `event_type` (String)
- `event_data` (JSONB)
- `user_id` (String, nullable)
- `ip_address` (String)
- `user_agent` (String)
- `timestamp` (Timestamp)

**webhook_events**
- `id` (UUID, PK)
- `transaction_id` (UUID, FK)
- `provider` (String)
- `event_type` (String)
- `payload` (JSONB)
- `signature` (String)
- `verified` (Boolean)
- `processed` (Boolean)
- `retry_count` (Integer)
- `created_at` (Timestamp)
- `processed_at` (Timestamp, nullable)

**provider_configs**
- `id` (UUID, PK)
- `provider_name` (String, Unique)
- `is_active` (Boolean)
- `api_key` (String, Encrypted)
- `api_secret` (String, Encrypted)
- `webhook_secret` (String, Encrypted)
- `config` (JSONB)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)

---

## Technical Specifications

### 1. Idempotency Implementation

**Mechanism:**
- Client sends `Idempotency-Key` header with each request
- Key format: UUID v4
- TTL: 24 hours in Redis
- Response: 
  - First request: Process and cache response
  - Duplicate request: Return cached response (409 or 200 based on status)

**Implementation:**
```python
@idempotent(ttl=86400)  # 24 hours
def process_payment(idempotency_key, payment_data):
    # Check Redis for existing response
    # If exists: return cached
    # If not: process, cache, return
```

### 2. Audit Trail

**Events Logged:**
- Payment initiated
- Payment processing
- Payment completed/failed
- Refund initiated/completed
- Configuration changes
- Webhook received
- API calls

**Data Captured:**
- Transaction ID
- User ID
- IP Address
- User Agent
- Timestamp
- Event type
- Event data (full request/response)
- Status changes

### 3. Webhook Handling

**Features:**
- Signature verification (HMAC-SHA256)
- Automatic retry with exponential backoff
- Retry schedule: 1min, 5min, 15min, 1hr, 6hr
- Dead letter queue for failed webhooks
- Webhook endpoint per provider: `/webhooks/{provider}`

**Security:**
- Validate webhook signature
- Verify source IP (if applicable)
- Rate limiting per provider
- Replay attack protection (timestamp validation)

### 4. WebSocket Real-Time Updates

**Channels:**
- `/ws/transaction/{transaction_id}` - Transaction-specific updates
- `/ws/user/{user_id}` - User-specific updates

**Events Emitted:**
- `payment.initiated`
- `payment.processing`
- `payment.completed`
- `payment.failed`
- `refund.processing`
- `refund.completed`

### 5. Provider Abstraction Layer

**Interface Definition:**
```python
class PaymentProvider(ABC):
    @abstractmethod
    def initialize_payment(self, amount, currency, customer_data, metadata):
        """Initialize payment and return payment URL/token"""
        pass
    
    @abstractmethod
    def verify_payment(self, transaction_id):
        """Verify payment status with provider"""
        pass
    
    @abstractmethod
    def refund_payment(self, transaction_id, amount):
        """Process refund"""
        pass
    
    @abstractmethod
    def verify_webhook(self, payload, signature):
        """Verify webhook authenticity"""
        pass
    
    @abstractmethod
    def handle_webhook(self, payload):
        """Process webhook event"""
        pass
```

**Provider Registry:**
```python
# Auto-discovery and registration
PROVIDERS = {
    'mpesa': MPesaProvider,
    'visa': VisaProvider,
    'cpay': CPayProvider,
}

# Dynamic loading
provider = PROVIDERS[provider_name](config)
```

---

## API Endpoints

### Payment Operations

**POST /api/v1/payments/initialize**
- Initialize a payment
- Headers: `Idempotency-Key`, `Authorization`
- Body:
```json
{
  "provider": "mpesa",
  "amount": 1000.00,
  "currency": "KES",
  "customer": {
    "phone": "+254700000000",
    "email": "customer@example.com",
    "name": "John Doe"
  },
  "metadata": {
    "order_id": "ORD-12345"
  }
}
```

**GET /api/v1/payments/{transaction_id}**
- Get payment status
- Response includes full transaction details and audit trail

**POST /api/v1/payments/{transaction_id}/refund**
- Process refund
- Body: `{"amount": 500.00, "reason": "Customer request"}`

**GET /api/v1/payments**
- List payments with filtering and pagination
- Query params: `provider`, `status`, `customer_id`, `page`, `limit`

### Webhook Endpoints

**POST /api/v1/webhooks/{provider}**
- Receive webhooks from payment providers
- Automatic signature verification
- Async processing

### Admin/Management

**GET /api/v1/providers**
- List available providers

**POST /api/v1/providers/{provider_name}/config**
- Configure provider credentials (admin only)

**GET /api/v1/health**
- Health check endpoint

**GET /api/v1/metrics**
- Basic metrics (transaction count, success rate, etc.)

---

## Security Considerations

1. **API Authentication:** JWT-based authentication
2. **Encryption:** 
   - TLS for all communications
   - Encrypted storage for sensitive credentials (Fernet)
3. **Secrets Management:** Environment variables, never hardcoded
4. **Input Validation:** Comprehensive validation using Marshmallow/Pydantic
5. **Rate Limiting:** Per-endpoint and per-user limits
6. **CORS:** Configurable CORS policies
7. **SQL Injection Prevention:** SQLAlchemy ORM, parameterized queries

---

## Performance Requirements

- **Response Time:** < 500ms for 95th percentile
- **Throughput:** Handle 100 concurrent requests
- **Availability:** 99.9% uptime target
- **Scalability:** Horizontal scaling capability

---

## Development Timeline (4 Days)

### Day 1: Foundation
- ✅ Project setup and structure
- ✅ Database models and migrations
- ✅ Base Flask application with blueprints
- ✅ Redis integration
- ✅ Configuration management
- ✅ Authentication middleware

### Day 2: Core Features + Provider Integration
- ✅ Payment service layer
- ✅ Provider abstraction interface
- ✅ M-Pesa integration (primary)
- ✅ Visa/Card integration (via Stripe/PayStack)
- ✅ CPay mock integration
- ✅ Idempotency middleware
- ✅ Basic API endpoints

### Day 3: Production Features
- ✅ Audit logging system
- ✅ Webhook receiver and processor
- ✅ WebSocket server for real-time updates
- ✅ Error handling and logging
- ✅ Rate limiting
- ✅ Admin endpoints
- ✅ Transaction verification flows

### Day 4: Testing & Documentation
- ✅ Unit tests (70%+ coverage target)
- ✅ Integration tests
- ✅ API documentation (Swagger/OpenAPI)
- ✅ Developer guide
- ✅ Deployment scripts
- ✅ Docker containerization
- ✅ Postman collection
- ✅ Final testing and bug fixes

---

## Testing Strategy

### Unit Tests
- Service layer logic
- Provider adapters
- Utility functions
- Validation schemas

### Integration Tests
- End-to-end payment flows
- Webhook processing
- WebSocket connections
- Database operations

### Manual Testing
- Postman collection for all endpoints
- WebSocket client testing
- Provider integration testing (sandbox)

---

## Deployment Considerations

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Docker (optional)

### Environment Variables
```
FLASK_ENV=production
DATABASE_URL=postgresql://user:pass@localhost/paymentdb
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret

# Provider Credentials
MPESA_CONSUMER_KEY=xxx
MPESA_CONSUMER_SECRET=xxx
MPESA_SHORTCODE=xxx
MPESA_PASSKEY=xxx

STRIPE_API_KEY=xxx
STRIPE_WEBHOOK_SECRET=xxx
```

### Docker Deployment
```bash
docker-compose up -d
```

---

## Success Criteria

1. ✅ All API endpoints functional and documented
2. ✅ Successfully process test payments through at least 2 providers
3. ✅ Idempotency working (duplicate requests handled correctly)
4. ✅ Audit trail capturing all transaction events
5. ✅ Webhooks processing correctly with retry mechanism
6. ✅ WebSocket real-time updates working
7. ✅ Tests passing with >70% coverage
8. ✅ Documentation complete and clear
9. ✅ Code follows Python best practices (PEP 8)
10. ✅ Ready for demo/presentation

---

## Future Enhancements (Post-Prototype)

- Additional payment providers (PayPal, Flutterwave, etc.)
- Subscription/recurring payments
- Multi-currency support with FX conversion
- Advanced fraud detection
- Comprehensive admin dashboard
- Mobile SDK
- GraphQL API
- Advanced analytics and reporting
- Payment link generation
- PCI DSS compliance measures

---

## Support & Maintenance

- Code repository with clear commit history
- Issue tracking setup
- Deployment documentation
- Monitoring and alerting setup recommendations
- Backup and recovery procedures

---

## Contact & Questions

For questions during development, refer to:
- Developer Guide (separate document)
- API Documentation (Swagger UI)
- Code comments and docstrings
- Provider documentation links in README
