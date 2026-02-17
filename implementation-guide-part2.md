# Payment Gateway - Implementation Guide Part 2

## DAY 2 CONTINUED: Services and API Endpoints

### Step 2.3: Idempotency Service (30 mins)

**File: `app/services/idempotency_service.py`**

```python
import json
from functools import wraps
from flask import request, jsonify
from app.extensions import redis_client


class IdempotencyService:
    """Handle request idempotency using Redis"""
    
    DEFAULT_TTL = 86400  # 24 hours
    
    @staticmethod
    def get_key(idempotency_key: str) -> str:
        """Generate Redis key for idempotency"""
        return f'idempotency:{idempotency_key}'
    
    @staticmethod
    def get_cached_response(idempotency_key: str):
        """Get cached response for idempotency key"""
        key = IdempotencyService.get_key(idempotency_key)
        cached = redis_client.get(key)
        
        if cached:
            return json.loads(cached)
        return None
    
    @staticmethod
    def cache_response(idempotency_key: str, response_data: dict, ttl: int = DEFAULT_TTL):
        """Cache response for future idempotent requests"""
        key = IdempotencyService.get_key(idempotency_key)
        redis_client.set(key, json.dumps(response_data), ex=ttl)
    
    @staticmethod
    def delete_cached_response(idempotency_key: str):
        """Delete cached response"""
        key = IdempotencyService.get_key(idempotency_key)
        redis_client.delete(key)


def idempotent(ttl: int = IdempotencyService.DEFAULT_TTL):
    """Decorator to make endpoints idempotent"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get idempotency key from header
            idempotency_key = request.headers.get('Idempotency-Key')
            
            if not idempotency_key:
                return jsonify({
                    'error': 'Missing Idempotency-Key header',
                    'message': 'All mutation requests require an Idempotency-Key header'
                }), 400
            
            # Check for cached response
            cached = IdempotencyService.get_cached_response(idempotency_key)
            
            if cached:
                # Return cached response with 200 status
                return jsonify(cached), cached.get('_status_code', 200)
            
            # Execute function
            result = f(*args, **kwargs)
            
            # Cache successful response
            if isinstance(result, tuple):
                response_data, status_code = result
                if hasattr(response_data, 'get_json'):
                    response_json = response_data.get_json()
                else:
                    response_json = response_data
                
                response_json['_status_code'] = status_code
                IdempotencyService.cache_response(idempotency_key, response_json, ttl)
            
            return result
        
        return decorated_function
    return decorator
```

### Step 2.4: Payment Service (1 hour)

**File: `app/services/payment_service.py`**

```python
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from app.extensions import db
from app.models import Transaction, TransactionStatus
from app.services.audit_service import AuditService
from app.providers import get_provider
from app.websocket.events import emit_transaction_update


class PaymentService:
    """Core payment processing service"""
    
    @staticmethod
    def initialize_payment(
        provider: str,
        amount: float,
        currency: str,
        customer_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None
    ) -> Transaction:
        """
        Initialize a new payment transaction
        
        Args:
            provider: Payment provider name (mpesa, stripe, cpay)
            amount: Payment amount
            currency: Currency code
            customer_data: Customer information
            metadata: Additional metadata
            idempotency_key: Idempotency key for request
        
        Returns:
            Transaction object
        """
        
        # Check if transaction with idempotency key already exists
        if idempotency_key:
            existing = Transaction.query.filter_by(idempotency_key=idempotency_key).first()
            if existing:
                return existing
        
        # Create transaction record
        transaction = Transaction(
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            provider=provider,
            amount=amount,
            currency=currency,
            customer_id=customer_data.get('id'),
            customer_phone=customer_data.get('phone'),
            customer_email=customer_data.get('email'),
            customer_name=customer_data.get('name'),
            payment_method=provider,
            metadata=metadata,
            status=TransactionStatus.PENDING
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Log audit event
        AuditService.log_event(
            transaction_id=transaction.id,
            event_type='payment.initiated',
            event_data={
                'provider': provider,
                'amount': amount,
                'currency': currency,
                'customer': customer_data
            }
        )
        
        # Emit WebSocket event
        emit_transaction_update(transaction, 'payment.initiated')
        
        try:
            # Initialize payment with provider
            provider_instance = get_provider(provider)
            result = provider_instance.initialize_payment(
                amount=amount,
                currency=currency,
                customer_data=customer_data,
                metadata=metadata
            )
            
            # Update transaction with provider response
            transaction.provider_transaction_id = result.get('transaction_id')
            transaction.provider_response = result
            transaction.status = TransactionStatus.PROCESSING
            
            db.session.commit()
            
            # Log processing event
            AuditService.log_event(
                transaction_id=transaction.id,
                event_type='payment.processing',
                event_data={
                    'provider_transaction_id': result.get('transaction_id'),
                    'provider_response': result
                }
            )
            
            # Emit WebSocket event
            emit_transaction_update(transaction, 'payment.processing')
            
        except Exception as e:
            transaction.status = TransactionStatus.FAILED
            transaction.provider_response = {'error': str(e)}
            db.session.commit()
            
            # Log failure
            AuditService.log_event(
                transaction_id=transaction.id,
                event_type='payment.failed',
                event_data={'error': str(e)}
            )
            
            # Emit WebSocket event
            emit_transaction_update(transaction, 'payment.failed')
            
            raise
        
        return transaction
    
    @staticmethod
    def verify_payment(transaction_id: uuid.UUID) -> Transaction:
        """
        Verify payment status with provider
        
        Args:
            transaction_id: Transaction UUID
        
        Returns:
            Updated transaction
        """
        transaction = Transaction.query.get(transaction_id)
        
        if not transaction:
            raise ValueError(f'Transaction {transaction_id} not found')
        
        # Don't verify completed or refunded transactions
        if transaction.status in [TransactionStatus.COMPLETED, TransactionStatus.REFUNDED]:
            return transaction
        
        try:
            provider_instance = get_provider(transaction.provider)
            result = provider_instance.verify_payment(transaction.provider_transaction_id)
            
            # Update transaction status
            old_status = transaction.status
            new_status = result.get('status')
            
            if new_status == 'completed':
                transaction.status = TransactionStatus.COMPLETED
                transaction.completed_at = datetime.utcnow()
            elif new_status == 'failed':
                transaction.status = TransactionStatus.FAILED
            
            transaction.provider_response = result
            db.session.commit()
            
            # Log status change
            if old_status != transaction.status:
                AuditService.log_event(
                    transaction_id=transaction.id,
                    event_type=f'payment.{transaction.status}',
                    event_data={
                        'old_status': old_status,
                        'new_status': transaction.status,
                        'provider_response': result
                    }
                )
                
                # Emit WebSocket event
                emit_transaction_update(transaction, f'payment.{transaction.status}')
        
        except Exception as e:
            AuditService.log_event(
                transaction_id=transaction.id,
                event_type='payment.verification_failed',
                event_data={'error': str(e)}
            )
            raise
        
        return transaction
    
    @staticmethod
    def refund_payment(
        transaction_id: uuid.UUID,
        amount: Optional[float] = None,
        reason: Optional[str] = None
    ) -> Transaction:
        """
        Process payment refund
        
        Args:
            transaction_id: Transaction UUID
            amount: Refund amount (None for full refund)
            reason: Refund reason
        
        Returns:
            Updated transaction
        """
        transaction = Transaction.query.get(transaction_id)
        
        if not transaction:
            raise ValueError(f'Transaction {transaction_id} not found')
        
        if transaction.status != TransactionStatus.COMPLETED:
            raise ValueError('Can only refund completed transactions')
        
        # Log refund initiation
        AuditService.log_event(
            transaction_id=transaction.id,
            event_type='refund.initiated',
            event_data={
                'amount': amount,
                'reason': reason
            }
        )
        
        try:
            provider_instance = get_provider(transaction.provider)
            result = provider_instance.refund_payment(
                provider_transaction_id=transaction.provider_transaction_id,
                amount=amount,
                reason=reason
            )
            
            transaction.status = TransactionStatus.REFUNDED
            transaction.provider_response = {
                **transaction.provider_response,
                'refund': result
            }
            db.session.commit()
            
            # Log refund completion
            AuditService.log_event(
                transaction_id=transaction.id,
                event_type='refund.completed',
                event_data=result
            )
            
            # Emit WebSocket event
            emit_transaction_update(transaction, 'refund.completed')
        
        except Exception as e:
            AuditService.log_event(
                transaction_id=transaction.id,
                event_type='refund.failed',
                event_data={'error': str(e)}
            )
            raise
        
        return transaction
    
    @staticmethod
    def get_transaction(transaction_id: uuid.UUID) -> Optional[Transaction]:
        """Get transaction by ID"""
        return Transaction.query.get(transaction_id)
    
    @staticmethod
    def list_transactions(
        provider: Optional[str] = None,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ):
        """
        List transactions with filters
        
        Returns:
            Paginated list of transactions
        """
        query = Transaction.query
        
        if provider:
            query = query.filter_by(provider=provider)
        
        if status:
            query = query.filter_by(status=status)
        
        if customer_id:
            query = query.filter_by(customer_id=customer_id)
        
        return query.order_by(Transaction.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
```

### Step 2.5: Provider Registry (20 mins)

**File: `app/providers/__init__.py`**

```python
from typing import Dict, Type
from app.providers.base import PaymentProvider
from app.providers.mpesa_provider import MPesaProvider
from app.providers.stripe_provider import StripeProvider
from app.providers.cpay_provider import CPayProvider
from flask import current_app


# Provider registry
PROVIDERS: Dict[str, Type[PaymentProvider]] = {
    'mpesa': MPesaProvider,
    'stripe': StripeProvider,
    'visa': StripeProvider,  # Alias for card payments
    'cpay': CPayProvider,
}


def get_provider(provider_name: str) -> PaymentProvider:
    """
    Get provider instance by name
    
    Args:
        provider_name: Name of the provider (mpesa, stripe, cpay, etc.)
    
    Returns:
        Initialized provider instance
    
    Raises:
        ValueError: If provider not found
    """
    provider_class = PROVIDERS.get(provider_name.lower())
    
    if not provider_class:
        raise ValueError(f'Unknown provider: {provider_name}')
    
    # Get provider configuration from app config
    config = _get_provider_config(provider_name.lower())
    
    return provider_class(config)


def _get_provider_config(provider_name: str) -> dict:
    """Get provider configuration from app config"""
    
    if provider_name == 'mpesa':
        return {
            'environment': current_app.config.get('MPESA_ENV', 'sandbox'),
            'consumer_key': current_app.config.get('MPESA_CONSUMER_KEY'),
            'consumer_secret': current_app.config.get('MPESA_CONSUMER_SECRET'),
            'shortcode': current_app.config.get('MPESA_SHORTCODE'),
            'passkey': current_app.config.get('MPESA_PASSKEY'),
            'callback_url': current_app.config.get('MPESA_CALLBACK_URL'),
        }
    
    elif provider_name in ['stripe', 'visa']:
        return {
            'api_key': current_app.config.get('STRIPE_API_KEY'),
            'webhook_secret': current_app.config.get('STRIPE_WEBHOOK_SECRET'),
        }
    
    elif provider_name == 'cpay':
        return {
            'api_key': current_app.config.get('CPAY_API_KEY'),
            'api_secret': current_app.config.get('CPAY_API_SECRET'),
        }
    
    return {}


def list_available_providers():
    """List all available providers"""
    return list(PROVIDERS.keys())


__all__ = ['get_provider', 'list_available_providers', 'PROVIDERS']
```

### Step 2.6: Payment API Endpoints (1 hour)

**File: `app/api/payments.py`**

```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
import uuid

from app.schemas.payment_schema import (
    InitializePaymentSchema,
    RefundPaymentSchema,
    TransactionSchema
)
from app.services.payment_service import PaymentService
from app.services.idempotency_service import idempotent


payments_bp = Blueprint('payments', __name__)

initialize_schema = InitializePaymentSchema()
refund_schema = RefundPaymentSchema()
transaction_schema = TransactionSchema()


@payments_bp.route('/initialize', methods=['POST'])
@idempotent(ttl=86400)
def initialize_payment():
    """
    Initialize a payment
    
    Headers:
        - Idempotency-Key: UUID v4 for request idempotency
    
    Body:
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
    """
    try:
        # Validate request data
        data = initialize_schema.load(request.json)
        
        # Get idempotency key
        idempotency_key = request.headers.get('Idempotency-Key')
        
        # Initialize payment
        transaction = PaymentService.initialize_payment(
            provider=data['provider'],
            amount=data['amount'],
            currency=data['currency'],
            customer_data=data['customer'],
            metadata=data.get('metadata'),
            idempotency_key=idempotency_key
        )
        
        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 201
    
    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation error',
            'details': e.messages
        }), 400
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@payments_bp.route('/<uuid:transaction_id>', methods=['GET'])
def get_payment(transaction_id):
    """
    Get payment details
    
    Path Parameters:
        - transaction_id: Transaction UUID
    """
    try:
        transaction = PaymentService.get_transaction(transaction_id)
        
        if not transaction:
            return jsonify({
                'success': False,
                'error': 'Transaction not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@payments_bp.route('/<uuid:transaction_id>/verify', methods=['POST'])
def verify_payment(transaction_id):
    """
    Verify payment status with provider
    
    Path Parameters:
        - transaction_id: Transaction UUID
    """
    try:
        transaction = PaymentService.verify_payment(transaction_id)
        
        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 200
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@payments_bp.route('/<uuid:transaction_id>/refund', methods=['POST'])
@idempotent(ttl=86400)
def refund_payment(transaction_id):
    """
    Process payment refund
    
    Headers:
        - Idempotency-Key: UUID v4 for request idempotency
    
    Path Parameters:
        - transaction_id: Transaction UUID
    
    Body:
        {
            "amount": 500.00,  // Optional, full refund if not specified
            "reason": "Customer request"
        }
    """
    try:
        data = refund_schema.load(request.json)
        
        transaction = PaymentService.refund_payment(
            transaction_id=transaction_id,
            amount=data.get('amount'),
            reason=data.get('reason')
        )
        
        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 200
    
    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation error',
            'details': e.messages
        }), 400
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@payments_bp.route('', methods=['GET'])
def list_payments():
    """
    List payments with filters
    
    Query Parameters:
        - provider: Filter by provider (optional)
        - status: Filter by status (optional)
        - customer_id: Filter by customer (optional)
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20, max: 100)
    """
    try:
        provider = request.args.get('provider')
        status = request.args.get('status')
        customer_id = request.args.get('customer_id')
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 20)), 100)
        
        pagination = PaymentService.list_transactions(
            provider=provider,
            status=status,
            customer_id=customer_id,
            page=page,
            per_page=per_page
        )
        
        return jsonify({
            'success': True,
            'data': {
                'items': transaction_schema.dump(pagination.items, many=True),
                'pagination': {
                    'page': pagination.page,
                    'per_page': pagination.per_page,
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
```

### Step 2.7: Schemas (30 mins)

**File: `app/schemas/payment_schema.py`**

```python
from marshmallow import Schema, fields, validates, ValidationError


class CustomerSchema(Schema):
    """Customer data schema"""
    id = fields.Str(required=False)
    phone = fields.Str(required=True)
    email = fields.Email(required=False)
    name = fields.Str(required=False)


class InitializePaymentSchema(Schema):
    """Payment initialization schema"""
    provider = fields.Str(required=True)
    amount = fields.Decimal(required=True, places=2)
    currency = fields.Str(required=True)
    customer = fields.Nested(CustomerSchema, required=True)
    metadata = fields.Dict(required=False)
    
    @validates('amount')
    def validate_amount(self, value):
        if value <= 0:
            raise ValidationError('Amount must be greater than 0')
    
    @validates('provider')
    def validate_provider(self, value):
        allowed_providers = ['mpesa', 'stripe', 'visa', 'cpay']
        if value.lower() not in allowed_providers:
            raise ValidationError(f'Provider must be one of: {", ".join(allowed_providers)}')


class RefundPaymentSchema(Schema):
    """Refund payment schema"""
    amount = fields.Decimal(required=False, places=2)
    reason = fields.Str(required=False)
    
    @validates('amount')
    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise ValidationError('Refund amount must be greater than 0')


class TransactionSchema(Schema):
    """Transaction response schema"""
    id = fields.UUID(dump_only=True)
    idempotency_key = fields.Str(dump_only=True)
    provider = fields.Str(dump_only=True)
    provider_transaction_id = fields.Str(dump_only=True)
    amount = fields.Decimal(places=2, dump_only=True)
    currency = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    customer = fields.Dict(dump_only=True)
    payment_method = fields.Str(dump_only=True)
    metadata = fields.Dict(dump_only=True)
    provider_response = fields.Dict(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    completed_at = fields.DateTime(dump_only=True)
```

---

## DAY 3: WEBHOOK & WEBSOCKET IMPLEMENTATION

### WebSocket Events (45 mins)

**File: `app/websocket/events.py`**

```python
from flask_socketio import emit, join_room, leave_room
from app.extensions import socketio
from app.models import Transaction


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('connected', {'message': 'Connected to payment gateway'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')


@socketio.on('subscribe_transaction')
def handle_subscribe_transaction(data):
    """Subscribe to transaction updates"""
    transaction_id = data.get('transaction_id')
    if transaction_id:
        room = f'transaction_{transaction_id}'
        join_room(room)
        emit('subscribed', {
            'message': f'Subscribed to transaction {transaction_id}',
            'room': room
        })


@socketio.on('unsubscribe_transaction')
def handle_unsubscribe_transaction(data):
    """Unsubscribe from transaction updates"""
    transaction_id = data.get('transaction_id')
    if transaction_id:
        room = f'transaction_{transaction_id}'
        leave_room(room)
        emit('unsubscribed', {
            'message': f'Unsubscribed from transaction {transaction_id}'
        })


def emit_transaction_update(transaction: Transaction, event_type: str):
    """
    Emit transaction update to subscribed clients
    
    Args:
        transaction: Transaction object
        event_type: Type of event (e.g., 'payment.completed')
    """
    room = f'transaction_{transaction.id}'
    
    socketio.emit('transaction_update', {
        'event_type': event_type,
        'transaction': transaction.to_dict()
    }, room=room)
    
    # Also emit to user-specific room if customer_id exists
    if transaction.customer_id:
        user_room = f'user_{transaction.customer_id}'
        socketio.emit('transaction_update', {
            'event_type': event_type,
            'transaction': transaction.to_dict()
        }, room=user_room)
```

---

## DEPLOYMENT GUIDE

### Docker Setup

**File: `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 5000

# Run application
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]
```

**File: `docker-compose.yml`**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    environment:
      POSTGRES_DB: payment_gateway_dev
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      FLASK_ENV: development
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/payment_gateway_dev
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - .:/app
    command: flask run --host=0.0.0.0

volumes:
  postgres_data:
```

### Environment Setup

**File: `.env.example`**

```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here

# Database
DATABASE_URL=postgresql://user:password@localhost/payment_gateway

# Redis
REDIS_URL=redis://localhost:6379/0

# M-Pesa (Daraja API)
MPESA_ENV=sandbox
MPESA_CONSUMER_KEY=your_consumer_key
MPESA_CONSUMER_SECRET=your_consumer_secret
MPESA_SHORTCODE=174379
MPESA_PASSKEY=your_passkey
MPESA_CALLBACK_URL=https://your-domain.com/api/v1/webhooks/mpesa

# Stripe
STRIPE_API_KEY=sk_test_your_key
STRIPE_WEBHOOK_SECRET=whsec_your_secret

# CPay (Mock)
CPAY_API_KEY=mock_api_key
CPAY_API_SECRET=mock_api_secret
```

### Quick Deploy Commands

```bash
# Using Docker Compose
docker-compose up -d

# Initialize database
docker-compose exec app flask db upgrade

# Check logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### Manual Deployment

```bash
# 1. Setup virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env with your credentials

# 4. Initialize database
flask db upgrade

# 5. Run application
python app.py
# Or with Gunicorn
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 app:app
```

---

## TESTING COMMANDS

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_payment_service.py

# Run integration tests
pytest tests/integration/
```

---

## API TESTING WITH CURL

### Initialize Payment

```bash
curl -X POST http://localhost:5000/api/v1/payments/initialize \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider": "mpesa",
    "amount": 1000,
    "currency": "KES",
    "customer": {
      "phone": "+254700000000",
      "email": "test@example.com",
      "name": "John Doe"
    },
    "metadata": {
      "order_id": "ORD-12345"
    }
  }'
```

### Get Payment

```bash
curl -X GET http://localhost:5000/api/v1/payments/{transaction_id}
```

### Verify Payment

```bash
curl -X POST http://localhost:5000/api/v1/payments/{transaction_id}/verify
```

### List Payments

```bash
curl -X GET "http://localhost:5000/api/v1/payments?provider=mpesa&status=completed&page=1&per_page=20"
```

---

## TROUBLESHOOTING

### Common Issues

1. **Database Connection Error**
   ```bash
   # Check PostgreSQL is running
   pg_isready
   
   # Check connection
   psql -U postgres -d payment_gateway_dev
   ```

2. **Redis Connection Error**
   ```bash
   # Check Redis is running
   redis-cli ping
   # Should return PONG
   ```

3. **Import Errors**
   ```bash
   # Reinstall dependencies
   pip install -r requirements.txt --force-reinstall
   ```

4. **Migration Issues**
   ```bash
   # Drop and recreate database
   dropdb payment_gateway_dev
   createdb payment_gateway_dev
   flask db upgrade
   ```

5. **M-Pesa Sandbox Issues**
   - Ensure you're using test credentials from Safaricom Daraja
   - Check callback URL is publicly accessible
   - Verify shortcode and passkey are correct
