"""
Pytest Configuration and Fixtures
"""

import pytest
import os
from app import create_app
from app.extensions import db as _db
from app.models import Transaction, AuditLog, WebhookEvent, ProviderConfig


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    # Set testing environment
    os.environ['FLASK_ENV'] = 'testing'

    app = create_app('testing')

    # Establish application context
    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()


@pytest.fixture(scope='session')
def db(app):
    """Create database for testing"""
    _db.create_all()

    yield _db

    _db.drop_all()


@pytest.fixture(scope='function')
def session(db):
    """Create a new database session for a test"""
    connection = db.engine.connect()
    transaction = connection.begin()

    session = db.create_scoped_session(
        options={'bind': connection, 'binds': {}}
    )

    db.session = session

    yield session

    transaction.rollback()
    connection.close()
    session.remove()


@pytest.fixture(scope='function')
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture(scope='function')
def sample_transaction(session):
    """Create a sample transaction for testing"""
    transaction = Transaction(
        idempotency_key='test-idempotency-key-123',
        provider='mpesa',
        amount=1000.00,
        currency='KES',
        customer_id='test-customer',
        customer_phone='+254700000000',
        customer_email='test@example.com',
        customer_name='Test User',
        payment_method='mpesa',
        status='pending',
        metadata={'order_id': 'ORD-123'}
    )

    session.add(transaction)
    session.commit()

    return transaction


@pytest.fixture(scope='function')
def sample_webhook_event(session, sample_transaction):
    """Create a sample webhook event for testing"""
    webhook = WebhookEvent(
        transaction_id=sample_transaction.id,
        provider='mpesa',
        event_type='payment.callback',
        payload={
            'Body': {
                'stkCallback': {
                    'ResultCode': 0,
                    'CheckoutRequestID': sample_transaction.provider_transaction_id
                }
            }
        },
        verified=True,
        processed=False
    )

    session.add(webhook)
    session.commit()

    return webhook


@pytest.fixture(scope='function')
def mock_mpesa_response():
    """Mock M-Pesa API response"""
    return {
        'MerchantRequestID': 'mock-merchant-id',
        'CheckoutRequestID': 'mock-checkout-id',
        'ResponseCode': '0',
        'ResponseDescription': 'Success. Request accepted for processing',
        'CustomerMessage': 'Success. Request accepted for processing'
    }


@pytest.fixture(scope='function')
def mock_stripe_payment_intent():
    """Mock Stripe PaymentIntent response"""
    return {
        'id': 'pi_mock_123',
        'object': 'payment_intent',
        'amount': 100000,
        'currency': 'usd',
        'status': 'requires_payment_method',
        'client_secret': 'pi_mock_123_secret_mock',
        'payment_method_types': ['card']
    }


@pytest.fixture
def redis_client(app):
    """Redis client for testing"""
    from app.extensions import redis_client
    yield redis_client
    # Cleanup: flush test keys
    redis_client.client.flushdb()