"""
Pytest Configuration and Fixtures
"""
from unittest.mock import patch

import fakeredis
import pytest
import os
from app import create_app
from app.extensions import db as _db
from app.models import Transaction, WebhookEvent


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    # Set testing environment
    os.environ['FLASK_ENV'] = 'testing'

    app = create_app()

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


from sqlalchemy.orm import scoped_session, sessionmaker


@pytest.fixture(scope='function')
def session(db):
    """Create a new database session for a test"""
    connection = db.engine.connect()
    transaction = connection.begin()

    Session = scoped_session(
        sessionmaker(bind=connection)
    )

    db.session = Session

    yield Session

    transaction.rollback()
    connection.close()
    Session.remove()

@pytest.fixture(scope="function")
def redis_client():
    """
    Fake Redis for tests + patch the app redis client.
    """
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)

    with patch("app.services.idempotency_service.redis_client", fake_redis):
        yield fake_redis

    fake_redis.flushall()

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


@pytest.fixture(autouse=True)
def clear_redis(redis_client):
    yield
    redis_client.flushall()

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

