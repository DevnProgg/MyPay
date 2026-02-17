"""
Unit Tests for Payment Service
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

from app.services.payment_service import PaymentService
from app.models import Transaction, TransactionStatus


class TestPaymentService:
    """Test cases for PaymentService"""

    def test_initialize_payment_success(self, session, mock_mpesa_response):
        """Test successful payment initialization"""

        with patch('app.providers.get_provider') as mock_get_provider:
            # Setup mock provider
            mock_provider = Mock()
            mock_provider.initialize_payment.return_value = {
                'transaction_id': 'MOCK-123',
                'status': 'processing',
                'payment_url': 'https://example.com/pay'
            }
            mock_get_provider.return_value = mock_provider

            # Initialize payment
            transaction = PaymentService.initialize_payment(
                provider='mpesa',
                amount=1000.00,
                currency='KES',
                customer_data={
                    'phone': '+254700000000',
                    'email': 'test@example.com',
                    'name': 'Test User'
                },
                metadata={'order_id': 'ORD-123'},
                idempotency_key='test-key-123'
            )

            # Assertions
            assert transaction is not None
            assert transaction.provider == 'mpesa'
            assert transaction.amount == Decimal('1000.00')
            assert transaction.currency == 'KES'
            assert transaction.status == TransactionStatus.PROCESSING
            assert transaction.idempotency_key == 'test-key-123'
            assert transaction.provider_transaction_id == 'MOCK-123'

    def test_initialize_payment_idempotency(self, session):
        """Test that idempotency prevents duplicate payments"""

        # Create existing transaction
        existing = Transaction(
            idempotency_key='duplicate-key',
            provider='mpesa',
            amount=1000.00,
            currency='KES',
            customer_phone='+254700000000',
            status='completed'
        )
        session.add(existing)
        session.commit()

        with patch('app.providers.get_provider') as mock_get_provider:
            mock_provider = Mock()
            mock_get_provider.return_value = mock_provider

            # Try to initialize with same idempotency key
            transaction = PaymentService.initialize_payment(
                provider='mpesa',
                amount=2000.00,  # Different amount
                currency='KES',
                customer_data={'phone': '+254711111111'},
                idempotency_key='duplicate-key'
            )

            # Should return existing transaction
            assert transaction.id == existing.id
            assert transaction.amount == Decimal('1000.00')  # Original amount
            # Provider should not be called
            mock_provider.initialize_payment.assert_not_called()

    def test_verify_payment_success(self, session, sample_transaction):
        """Test successful payment verification"""

        sample_transaction.provider_transaction_id = 'MOCK-123'
        sample_transaction.status = TransactionStatus.PROCESSING
        session.commit()

        with patch('app.providers.get_provider') as mock_get_provider:
            mock_provider = Mock()
            mock_provider.verify_payment.return_value = {
                'status': 'completed',
                'amount': 1000.00,
                'currency': 'KES'
            }
            mock_get_provider.return_value = mock_provider

            # Verify payment
            transaction = PaymentService.verify_payment(sample_transaction.id)

            # Assertions
            assert transaction.status == TransactionStatus.COMPLETED
            assert transaction.completed_at is not None
            mock_provider.verify_payment.assert_called_once_with('MOCK-123')

    def test_verify_payment_not_found(self, session):
        """Test verification of non-existent payment"""

        fake_id = uuid.uuid4()

        with pytest.raises(ValueError, match='not found'):
            PaymentService.verify_payment(fake_id)

    def test_refund_payment_success(self, session, sample_transaction):
        """Test successful payment refund"""

        sample_transaction.provider_transaction_id = 'MOCK-123'
        sample_transaction.status = TransactionStatus.COMPLETED
        session.commit()

        with patch('app.providers.get_provider') as mock_get_provider:
            mock_provider = Mock()
            mock_provider.refund_payment.return_value = {
                'refund_id': 'REF-123',
                'status': 'completed',
                'amount': 1000.00
            }
            mock_get_provider.return_value = mock_provider

            # Refund payment
            transaction = PaymentService.refund_payment(
                transaction_id=sample_transaction.id,
                amount=1000.00,
                reason='Customer request'
            )

            # Assertions
            assert transaction.status == TransactionStatus.REFUNDED
            mock_provider.refund_payment.assert_called_once()

    def test_refund_payment_not_completed(self, session, sample_transaction):
        """Test refund of non-completed payment fails"""

        sample_transaction.status = TransactionStatus.PENDING
        session.commit()

        with pytest.raises(ValueError, match='only refund completed'):
            PaymentService.refund_payment(sample_transaction.id)

    def test_get_transaction(self, session, sample_transaction):
        """Test getting transaction by ID"""

        transaction = PaymentService.get_transaction(sample_transaction.id)

        assert transaction is not None
        assert transaction.id == sample_transaction.id

    def test_list_transactions(self, session):
        """Test listing transactions with filters"""

        # Create multiple transactions
        for i in range(5):
            tx = Transaction(
                idempotency_key=f'key-{i}',
                provider='mpesa',
                amount=1000.00,
                currency='KES',
                customer_id='test-customer',
                status='completed' if i % 2 == 0 else 'pending'
            )
            session.add(tx)
        session.commit()

        # Test without filters
        result = PaymentService.list_transactions()
        assert result.total == 5

        # Test with status filter
        result = PaymentService.list_transactions(status='completed')
        assert result.total == 3

        # Test with provider filter
        result = PaymentService.list_transactions(provider='mpesa')
        assert result.total == 5

        # Test with customer filter
        result = PaymentService.list_transactions(customer_id='test-customer')
        assert result.total == 5

    def test_list_transactions_pagination(self, session):
        """Test transaction list pagination"""

        # Create 25 transactions
        for i in range(25):
            tx = Transaction(
                idempotency_key=f'key-{i}',
                provider='mpesa',
                amount=1000.00,
                currency='KES'
            )
            session.add(tx)
        session.commit()

        # Test first page
        result = PaymentService.list_transactions(page=1, per_page=10)
        assert len(result.items) == 10
        assert result.has_next is True
        assert result.has_prev is False

        # Test second page
        result = PaymentService.list_transactions(page=2, per_page=10)
        assert len(result.items) == 10
        assert result.has_next is True
        assert result.has_prev is True

        # Test last page
        result = PaymentService.list_transactions(page=3, per_page=10)
        assert len(result.items) == 5
        assert result.has_next is False
        assert result.has_prev is True