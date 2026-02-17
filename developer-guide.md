# Payment Gateway Prototype - Developer Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Project Structure](#project-structure)
3. [Development Roadmap](#development-roadmap)
4. [Day-by-Day Implementation](#day-by-day-implementation)
5. [Code Examples](#code-examples)
6. [Testing Guide](#testing-guide)
7. [Deployment](#deployment)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

```bash
# Install Python 3.11+
python --version

# Install PostgreSQL 14+
psql --version

# Install Redis 7+
redis-cli --version

# Install Git
git --version
```

### Initial Setup (15 minutes)

```bash
# 1. Create project directory
mkdir payment-gateway-prototype
cd payment-gateway-prototype

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Create requirements.txt
cat > requirements.txt << EOF
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.0.5
Flask-CORS==4.0.0
Flask-JWT-Extended==4.6.0
Flask-SocketIO==5.3.6
psycopg2-binary==2.9.9
redis==5.0.1
python-dotenv==1.0.0
marshmallow==3.20.1
requests==2.31.0
cryptography==41.0.7
gunicorn==21.2.0
eventlet==0.33.3
celery==5.3.4
pytest==7.4.3
pytest-cov==4.1.0
httpx==0.25.2
faker==20.1.0
EOF

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file
cat > .env << EOF
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=dev-secret-key-change-in-production
JWT_SECRET_KEY=dev-jwt-secret-change-in-production

DATABASE_URL=postgresql://localhost/payment_gateway_dev
REDIS_URL=redis://localhost:6379/0

# M-Pesa Credentials (Daraja API - Sandbox)
MPESA_ENV=sandbox
MPESA_CONSUMER_KEY=your_consumer_key
MPESA_CONSUMER_SECRET=your_consumer_secret
MPESA_SHORTCODE=174379
MPESA_PASSKEY=your_passkey
MPESA_CALLBACK_URL=https://your-domain.com/api/v1/webhooks/mpesa

# Stripe Credentials (Test Mode)
STRIPE_API_KEY=sk_test_your_key
STRIPE_WEBHOOK_SECRET=whsec_your_secret

# CPay (Mock - for demonstration)
CPAY_API_KEY=mock_api_key
CPAY_API_SECRET=mock_api_secret
EOF

# 6. Create database
createdb payment_gateway_dev

# 7. Initialize project structure
mkdir -p app/{models,services,providers,api,utils,schemas}
touch app/__init__.py
```

---

## Project Structure

```
payment-gateway-prototype/
├── app/
│   ├── __init__.py                 # Flask app factory
│   ├── config.py                   # Configuration management
│   ├── extensions.py               # Flask extensions initialization
│   │
│   ├── models/                     # Database models
│   │   ├── __init__.py
│   │   ├── transaction.py
│   │   ├── audit_log.py
│   │   ├── webhook_event.py
│   │   └── provider_config.py
│   │
│   ├── schemas/                    # Marshmallow schemas for validation
│   │   ├── __init__.py
│   │   ├── payment_schema.py
│   │   └── webhook_schema.py
│   │
│   ├── services/                   # Business logic layer
│   │   ├── __init__.py
│   │   ├── payment_service.py      # Core payment processing
│   │   ├── audit_service.py        # Audit logging
│   │   ├── webhook_service.py      # Webhook processing
│   │   └── idempotency_service.py  # Idempotency handling
│   │
│   ├── providers/                  # Payment provider integrations
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract base provider
│   │   ├── mpesa_provider.py       # M-Pesa integration
│   │   ├── stripe_provider.py      # Stripe/Visa integration
│   │   └── cpay_provider.py        # CPay mock integration
│   │
│   ├── api/                        # API routes/controllers
│   │   ├── __init__.py
│   │   ├── payments.py             # Payment endpoints
│   │   ├── webhooks.py             # Webhook endpoints
│   │   ├── admin.py                # Admin endpoints
│   │   └── health.py               # Health check endpoints
│   │
│   ├── utils/                      # Utility functions
│   │   ├── __init__.py
│   │   ├── decorators.py           # Custom decorators
│   │   ├── encryption.py           # Encryption utilities
│   │   ├── validators.py           # Custom validators
│   │   └── logger.py               # Logging configuration
│   │
│   └── websocket/                  # WebSocket handlers
│       ├── __init__.py
│       └── events.py
│
├── migrations/                     # Database migrations (auto-generated)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures
│   ├── unit/
│   │   ├── test_payment_service.py
│   │   ├── test_providers.py
│   │   └── test_idempotency.py
│   └── integration/
│       ├── test_payment_flow.py
│       └── test_webhooks.py
│
├── docs/
│   ├── api/                        # API documentation
│   └── diagrams/                   # Architecture diagrams
│
├── scripts/
│   ├── init_db.py                  # Database initialization
│   └── seed_data.py                # Seed test data
│
├── .env                            # Environment variables
├── .env.example                    # Environment template
├── .gitignore
├── requirements.txt                # Python dependencies
├── pytest.ini                      # Pytest configuration
├── docker-compose.yml              # Docker setup
├── Dockerfile
├── app.py                          # Application entry point
└── README.md
```

---

## Development Roadmap

### Day 1: Foundation (8 hours)

**Morning (4 hours): Project Setup & Database**
- ✅ Create project structure
- ✅ Setup Flask application factory
- ✅ Configure database and Redis
- ✅ Create database models
- ✅ Setup migrations

**Afternoon (4 hours): Core Infrastructure**
- ✅ Authentication middleware (JWT)
- ✅ Configuration management
- ✅ Logging setup
- ✅ Error handling middleware
- ✅ Base API structure

### Day 2: Payment Integration (8 hours)

**Morning (4 hours): Provider Abstraction**
- ✅ Create base provider interface
- ✅ Implement provider registry
- ✅ Create payment service layer
- ✅ Idempotency middleware

**Afternoon (4 hours): Provider Implementations**
- ✅ M-Pesa provider (STK Push)
- ✅ Stripe provider (Card payments)
- ✅ CPay mock provider
- ✅ Payment initialization endpoints

### Day 3: Production Features (8 hours)

**Morning (4 hours): Audit & Webhooks**
- ✅ Audit logging system
- ✅ Webhook receiver endpoints
- ✅ Webhook signature verification
- ✅ Retry mechanism

**Afternoon (4 hours): Real-time & Admin**
- ✅ WebSocket implementation
- ✅ Real-time notifications
- ✅ Admin endpoints
- ✅ Rate limiting

### Day 4: Testing & Documentation (8 hours)

**Morning (4 hours): Testing**
- ✅ Unit tests
- ✅ Integration tests
- ✅ End-to-end testing
- ✅ Bug fixes

**Afternoon (4 hours): Documentation & Deployment**
- ✅ API documentation (Swagger)
- ✅ README and guides
- ✅ Docker setup
- ✅ Postman collection
- ✅ Final review

---

## Day-by-Day Implementation

## DAY 1: FOUNDATION

### Step 1.1: Flask Application Factory (30 mins)

**File: `app/__init__.py`**

```python
from flask import Flask
from flask_cors import CORS
from app.extensions import db, migrate, jwt, redis_client, socketio
from app.config import config


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    redis_client.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    CORS(app)
    
    # Register blueprints
    from app.api import payments_bp, webhooks_bp, admin_bp, health_bp
    app.register_blueprint(payments_bp, url_prefix='/api/v1/payments')
    app.register_blueprint(webhooks_bp, url_prefix='/api/v1/webhooks')
    app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')
    app.register_blueprint(health_bp, url_prefix='/api/v1')
    
    # Error handlers
    register_error_handlers(app)
    
    return app


def register_error_handlers(app):
    """Register error handlers"""
    from flask import jsonify
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Bad request', 'message': str(error)}), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({'error': 'Unauthorized', 'message': str(error)}), 401
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found', 'message': str(error)}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error', 'message': str(error)}), 500
```

**File: `app/extensions.py`**

```python
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from redis import Redis

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
socketio = SocketIO()

class RedisClient:
    def __init__(self):
        self.client = None
    
    def init_app(self, app):
        import redis
        redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        self.client = redis.from_url(redis_url, decode_responses=True)
    
    def get(self, key):
        return self.client.get(key)
    
    def set(self, key, value, ex=None):
        return self.client.set(key, value, ex=ex)
    
    def delete(self, key):
        return self.client.delete(key)
    
    def exists(self, key):
        return self.client.exists(key)

redis_client = RedisClient()
```

**File: `app/config.py`**

```python
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost/payment_gateway_dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # M-Pesa Configuration
    MPESA_ENV = os.getenv('MPESA_ENV', 'sandbox')
    MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY')
    MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET')
    MPESA_SHORTCODE = os.getenv('MPESA_SHORTCODE')
    MPESA_PASSKEY = os.getenv('MPESA_PASSKEY')
    MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL')
    
    # Stripe Configuration
    STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    # CPay Configuration
    CPAY_API_KEY = os.getenv('CPAY_API_KEY')
    CPAY_API_SECRET = os.getenv('CPAY_API_SECRET')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'postgresql://localhost/payment_gateway_test'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
```

### Step 1.2: Database Models (1 hour)

**File: `app/models/transaction.py`**

```python
import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from enum import Enum


class TransactionStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'


class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    
    # Provider information
    provider = db.Column(db.String(50), nullable=False)
    provider_transaction_id = db.Column(db.String(255), index=True)
    provider_response = db.Column(JSONB)
    
    # Payment details
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='KES')
    status = db.Column(db.String(20), nullable=False, default=TransactionStatus.PENDING)
    
    # Customer information
    customer_id = db.Column(db.String(255), index=True)
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(255))
    customer_name = db.Column(db.String(255))
    
    # Payment method
    payment_method = db.Column(db.String(50))  # mpesa, card, etc.
    
    # Additional data
    metadata = db.Column(JSONB)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    audit_logs = db.relationship('AuditLog', backref='transaction', lazy='dynamic', cascade='all, delete-orphan')
    webhook_events = db.relationship('WebhookEvent', backref='transaction', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'idempotency_key': self.idempotency_key,
            'provider': self.provider,
            'provider_transaction_id': self.provider_transaction_id,
            'amount': float(self.amount),
            'currency': self.currency,
            'status': self.status,
            'customer': {
                'id': self.customer_id,
                'phone': self.customer_phone,
                'email': self.customer_email,
                'name': self.customer_name
            },
            'payment_method': self.payment_method,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
    
    def __repr__(self):
        return f'<Transaction {self.id} - {self.status}>'
```

**File: `app/models/audit_log.py`**

```python
import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey('transactions.id'), nullable=False, index=True)
    
    # Event details
    event_type = db.Column(db.String(100), nullable=False)
    event_data = db.Column(JSONB)
    
    # Request context
    user_id = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    # Timestamp
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'transaction_id': str(self.transaction_id),
            'event_type': self.event_type,
            'event_data': self.event_data,
            'user_id': self.user_id,
            'ip_address': self.ip_address,
            'timestamp': self.timestamp.isoformat()
        }
    
    def __repr__(self):
        return f'<AuditLog {self.id} - {self.event_type}>'
```

**File: `app/models/webhook_event.py`**

```python
import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class WebhookEvent(db.Model):
    __tablename__ = 'webhook_events'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey('transactions.id'), index=True)
    
    # Provider information
    provider = db.Column(db.String(50), nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False)
    
    # Webhook data
    payload = db.Column(JSONB, nullable=False)
    signature = db.Column(db.String(500))
    verified = db.Column(db.Boolean, default=False)
    
    # Processing status
    processed = db.Column(db.Boolean, default=False, index=True)
    retry_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'transaction_id': str(self.transaction_id) if self.transaction_id else None,
            'provider': self.provider,
            'event_type': self.event_type,
            'verified': self.verified,
            'processed': self.processed,
            'retry_count': self.retry_count,
            'created_at': self.created_at.isoformat(),
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }
    
    def __repr__(self):
        return f'<WebhookEvent {self.id} - {self.provider}>'
```

**File: `app/models/provider_config.py`**

```python
import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.utils.encryption import encrypt_value, decrypt_value


class ProviderConfig(db.Model):
    __tablename__ = 'provider_configs'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Encrypted credentials
    _api_key = db.Column('api_key', db.String(500))
    _api_secret = db.Column('api_secret', db.String(500))
    _webhook_secret = db.Column('webhook_secret', db.String(500))
    
    # Additional configuration
    config = db.Column(JSONB)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def api_key(self):
        if self._api_key:
            return decrypt_value(self._api_key)
        return None
    
    @api_key.setter
    def api_key(self, value):
        if value:
            self._api_key = encrypt_value(value)
        else:
            self._api_key = None
    
    @property
    def api_secret(self):
        if self._api_secret:
            return decrypt_value(self._api_secret)
        return None
    
    @api_secret.setter
    def api_secret(self, value):
        if value:
            self._api_secret = encrypt_value(value)
        else:
            self._api_secret = None
    
    @property
    def webhook_secret(self):
        if self._webhook_secret:
            return decrypt_value(self._webhook_secret)
        return None
    
    @webhook_secret.setter
    def webhook_secret(self, value):
        if value:
            self._webhook_secret = encrypt_value(value)
        else:
            self._webhook_secret = None
    
    def to_dict(self, include_secrets=False):
        data = {
            'id': str(self.id),
            'provider_name': self.provider_name,
            'is_active': self.is_active,
            'config': self.config,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
        if include_secrets:
            data['api_key'] = self.api_key
            data['api_secret'] = self.api_secret
            data['webhook_secret'] = self.webhook_secret
        
        return data
    
    def __repr__(self):
        return f'<ProviderConfig {self.provider_name}>'
```

**File: `app/models/__init__.py`**

```python
from app.models.transaction import Transaction, TransactionStatus
from app.models.audit_log import AuditLog
from app.models.webhook_event import WebhookEvent
from app.models.provider_config import ProviderConfig

__all__ = ['Transaction', 'TransactionStatus', 'AuditLog', 'WebhookEvent', 'ProviderConfig']
```

### Step 1.3: Encryption Utilities (20 mins)

**File: `app/utils/encryption.py`**

```python
from cryptography.fernet import Fernet
import os
import base64


def get_encryption_key():
    """Get or generate encryption key"""
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        # Generate a key for development
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    return key.encode() if isinstance(key, str) else key


_cipher = Fernet(get_encryption_key())


def encrypt_value(value: str) -> str:
    """Encrypt a string value"""
    if not value:
        return None
    return _cipher.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt an encrypted value"""
    if not encrypted_value:
        return None
    return _cipher.decrypt(encrypted_value.encode()).decode()
```

### Step 1.4: Initialize Database (15 mins)

```bash
# Initialize migrations
flask db init

# Create initial migration
flask db migrate -m "Initial migration"

# Apply migration
flask db upgrade
```

**File: `app.py`**

```python
import os
from app import create_app, socketio
from app.extensions import db

app = create_app(os.getenv('FLASK_ENV', 'development'))

@app.shell_context_processor
def make_shell_context():
    from app.models import Transaction, AuditLog, WebhookEvent, ProviderConfig
    return {
        'db': db,
        'Transaction': Transaction,
        'AuditLog': AuditLog,
        'WebhookEvent': WebhookEvent,
        'ProviderConfig': ProviderConfig
    }

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
```

---

## DAY 2: PAYMENT INTEGRATION

### Step 2.1: Provider Base Class (45 mins)

**File: `app/providers/base.py`**

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class PaymentProvider(ABC):
    """Abstract base class for payment providers"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration
        
        Args:
            config: Provider-specific configuration
        """
        self.config = config
        self.provider_name = self.__class__.__name__.replace('Provider', '').lower()
    
    @abstractmethod
    def initialize_payment(
        self,
        amount: float,
        currency: str,
        customer_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a payment transaction
        
        Args:
            amount: Payment amount
            currency: Currency code (e.g., 'KES', 'USD')
            customer_data: Customer information
            metadata: Additional metadata
        
        Returns:
            Dict containing:
                - transaction_id: Provider's transaction ID
                - status: Payment status
                - payment_url: URL for customer to complete payment (if applicable)
                - additional_data: Any additional provider-specific data
        """
        pass
    
    @abstractmethod
    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:
        """
        Verify payment status with the provider
        
        Args:
            provider_transaction_id: Provider's transaction ID
        
        Returns:
            Dict containing:
                - status: Payment status
                - amount: Payment amount
                - currency: Currency code
                - additional_data: Provider-specific data
        """
        pass
    
    @abstractmethod
    def refund_payment(
        self,
        provider_transaction_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a refund
        
        Args:
            provider_transaction_id: Provider's transaction ID
            amount: Refund amount (None for full refund)
            reason: Refund reason
        
        Returns:
            Dict containing:
                - refund_id: Refund transaction ID
                - status: Refund status
                - amount: Refunded amount
        """
        pass
    
    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature
        
        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers
        
        Returns:
            True if signature is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process webhook event
        
        Args:
            payload: Webhook payload
        
        Returns:
            Dict containing:
                - transaction_id: Provider's transaction ID
                - event_type: Type of event
                - status: Updated payment status
                - additional_data: Event-specific data
        """
        pass
    
    def get_provider_name(self) -> str:
        """Get provider name"""
        return self.provider_name


class PaymentProviderError(Exception):
    """Base exception for provider errors"""
    pass


class PaymentInitializationError(PaymentProviderError):
    """Raised when payment initialization fails"""
    pass


class PaymentVerificationError(PaymentProviderError):
    """Raised when payment verification fails"""
    pass


class RefundError(PaymentProviderError):
    """Raised when refund processing fails"""
    pass


class WebhookVerificationError(PaymentProviderError):
    """Raised when webhook verification fails"""
    pass
```

### Step 2.2: M-Pesa Provider (2 hours)

**File: `app/providers/mpesa_provider.py`**

```python
import base64
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import hmac
import hashlib

from app.providers.base import (
    PaymentProvider,
    PaymentInitializationError,
    PaymentVerificationError,
    RefundError,
    WebhookVerificationError
)


class MPesaProvider(PaymentProvider):
    """M-Pesa Daraja API integration"""
    
    SANDBOX_BASE_URL = 'https://sandbox.safaricom.co.ke'
    PRODUCTION_BASE_URL = 'https://api.safaricom.co.ke'
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        self.consumer_key = config.get('consumer_key')
        self.consumer_secret = config.get('consumer_secret')
        self.shortcode = config.get('shortcode')
        self.passkey = config.get('passkey')
        self.callback_url = config.get('callback_url')
        self.environment = config.get('environment', 'sandbox')
        
        self.base_url = (
            self.SANDBOX_BASE_URL if self.environment == 'sandbox'
            else self.PRODUCTION_BASE_URL
        )
        
        self._access_token = None
        self._token_expiry = None
    
    def _get_access_token(self) -> str:
        """Get OAuth access token"""
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._access_token
        
        url = f'{self.base_url}/oauth/v1/generate?grant_type=client_credentials'
        auth_string = f'{self.consumer_key}:{self.consumer_secret}'
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_auth}'
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            self._access_token = data['access_token']
            # Token expires in 3599 seconds, we'll refresh at 3000
            from datetime import timedelta
            self._token_expiry = datetime.now() + timedelta(seconds=3000)
            
            return self._access_token
        except requests.RequestException as e:
            raise PaymentInitializationError(f'Failed to get M-Pesa access token: {str(e)}')
    
    def _generate_password(self) -> tuple:
        """Generate password and timestamp for STK Push"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_string = f'{self.shortcode}{self.passkey}{timestamp}'
        password = base64.b64encode(password_string.encode()).decode()
        return password, timestamp
    
    def initialize_payment(
        self,
        amount: float,
        currency: str,
        customer_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize M-Pesa STK Push payment"""
        
        if currency != 'KES':
            raise PaymentInitializationError('M-Pesa only supports KES currency')
        
        phone = customer_data.get('phone', '').replace('+', '')
        if not phone.startswith('254'):
            raise PaymentInitializationError('Phone number must be in format 254XXXXXXXXX')
        
        token = self._get_access_token()
        password, timestamp = self._generate_password()
        
        url = f'{self.base_url}/mpesa/stkpush/v1/processrequest'
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone,
            'PartyB': self.shortcode,
            'PhoneNumber': phone,
            'CallBackURL': self.callback_url,
            'AccountReference': metadata.get('order_id', 'Payment') if metadata else 'Payment',
            'TransactionDesc': metadata.get('description', 'Payment') if metadata else 'Payment'
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ResponseCode') == '0':
                return {
                    'transaction_id': data.get('CheckoutRequestID'),
                    'merchant_request_id': data.get('MerchantRequestID'),
                    'status': 'pending',
                    'additional_data': {
                        'customer_message': data.get('CustomerMessage'),
                        'response_description': data.get('ResponseDescription')
                    }
                }
            else:
                raise PaymentInitializationError(
                    f"M-Pesa error: {data.get('ResponseDescription', 'Unknown error')}"
                )
        
        except requests.RequestException as e:
            raise PaymentInitializationError(f'M-Pesa STK Push failed: {str(e)}')
    
    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:
        """Query STK Push transaction status"""
        
        token = self._get_access_token()
        password, timestamp = self._generate_password()
        
        url = f'{self.base_url}/mpesa/stkpushquery/v1/query'
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'CheckoutRequestID': provider_transaction_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            result_code = data.get('ResultCode')
            
            if result_code == '0':
                status = 'completed'
            elif result_code == '1032':
                status = 'cancelled'
            elif result_code is None or data.get('ResponseCode') == '0':
                status = 'pending'
            else:
                status = 'failed'
            
            return {
                'status': status,
                'result_code': result_code,
                'result_desc': data.get('ResultDesc'),
                'additional_data': data
            }
        
        except requests.RequestException as e:
            raise PaymentVerificationError(f'M-Pesa verification failed: {str(e)}')
    
    def refund_payment(
        self,
        provider_transaction_id: str,
        amount: Optional[float] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process M-Pesa reversal (refund)"""
        
        # M-Pesa reversals require additional setup and permissions
        # This is a simplified implementation
        raise RefundError('M-Pesa reversals require special permissions. Contact support.')
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify M-Pesa webhook signature"""
        # M-Pesa doesn't use signature verification
        # Instead, verify by checking if callback comes from Safaricom IPs
        # For production, implement IP whitelisting
        return True
    
    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process M-Pesa callback"""
        
        body = payload.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        
        result_code = stk_callback.get('ResultCode')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        
        if result_code == 0:
            status = 'completed'
            callback_metadata = stk_callback.get('CallbackMetadata', {})
            items = callback_metadata.get('Item', [])
            
            # Extract transaction details
            amount = None
            mpesa_receipt = None
            phone = None
            
            for item in items:
                name = item.get('Name')
                if name == 'Amount':
                    amount = item.get('Value')
                elif name == 'MpesaReceiptNumber':
                    mpesa_receipt = item.get('Value')
                elif name == 'PhoneNumber':
                    phone = item.get('Value')
            
            additional_data = {
                'amount': amount,
                'mpesa_receipt_number': mpesa_receipt,
                'phone_number': phone,
                'transaction_date': stk_callback.get('CallbackMetadata', {}).get('Item', [{}])[0].get('Value')
            }
        else:
            status = 'failed'
            additional_data = {
                'result_desc': stk_callback.get('ResultDesc')
            }
        
        return {
            'transaction_id': checkout_request_id,
            'event_type': 'payment.callback',
            'status': status,
            'result_code': result_code,
            'additional_data': additional_data
        }
```

[Due to length constraints, I'll continue with the remaining critical files in the next section. The guide includes complete implementations for Stripe, CPay providers, services, API endpoints, schemas, and testing. Would you like me to continue with specific sections, or shall I provide this as multiple files?]
