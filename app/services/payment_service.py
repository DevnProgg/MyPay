import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from app.extensions import db
from app.models import Transaction, TransactionStatus
from app.services.audit_service import AuditService
from app.providers import get_provider
from app.websockets.events import emit_transaction_update


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
                transaction.completed_at = datetime.now()
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