"""
CPay Mock Provider Implementation
This is a mock implementation to demonstrate the plug-and-play architecture
Replace with actual CPay API integration when available
"""

import uuid
import random
import time
import hmac
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

from app.providers.base import (
    PaymentProvider,
    PaymentInitializationError,
    PaymentVerificationError,
    RefundError,
    WebhookVerificationError
)


class CPayProvider(PaymentProvider):
    """Mock CPay payment provider for demonstration"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.api_key = config.get('api_key')
        self.api_secret = config.get('api_secret')

        # Mock transaction storage (in real implementation, this would be API calls)
        self._mock_transactions = {}

    def initialize_payment(
            self,
            amount: float,
            currency: str,
            customer_data: Dict[str, Any],
            metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a CPay payment (mock implementation)

        In a real implementation, this would:
        1. Make API call to CPay's payment initialization endpoint
        2. Get payment URL or payment token
        3. Return payment details

        Args:
            amount: Payment amount
            currency: Currency code
            customer_data: Customer information
            metadata: Additional metadata

        Returns:
            Dict containing payment details
        """
        # Generate mock transaction ID
        transaction_id = f'CPAY-{uuid.uuid4().hex[:12].upper()}'

        # Generate mock payment URL
        payment_url = f'https://checkout.cpay.example.com/pay/{transaction_id}'

        # Store mock transaction
        self._mock_transactions[transaction_id] = {
            'id': transaction_id,
            'amount': amount,
            'currency': currency,
            'customer': customer_data,
            'metadata': metadata or {},
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat(),
            'payment_url': payment_url
        }

        return {
            'transaction_id': transaction_id,
            'status': 'pending',
            'payment_url': payment_url,
            'additional_data': {
                'payment_reference': transaction_id,
                'expires_at': self._get_expiry_time(),
                'customer_message': 'Please complete payment at the provided URL',
                'checkout_token': self._generate_checkout_token(transaction_id)
            }
        }

    def verify_payment(self, provider_transaction_id: str) -> Dict[str, Any]:
        """
        Verify CPay payment status (mock implementation)

        In a real implementation, this would:
        1. Make API call to CPay's verification endpoint
        2. Get actual payment status from CPay
        3. Return updated status

        Args:
            provider_transaction_id: CPay transaction ID

        Returns:
            Dict containing payment status
        """
        # Check mock transaction storage
        transaction = self._mock_transactions.get(provider_transaction_id)

        if not transaction:
            raise PaymentVerificationError(f'Transaction {provider_transaction_id} not found')

        # Simulate random payment status for demo
        # In production, this would be actual API response
        current_status = transaction.get('status', 'pending')

        if current_status == 'pending':
            # 70% chance of success, 20% still pending, 10% failed
            rand = random.random()
            if rand < 0.7:
                current_status = 'completed'
                transaction['status'] = 'completed'
                transaction['completed_at'] = datetime.utcnow().isoformat()
                transaction['cpay_receipt'] = f'REC-{uuid.uuid4().hex[:10].upper()}'
            elif rand < 0.9:
                current_status = 'pending'
            else:
                current_status = 'failed'
                transaction['status'] = 'failed'
                transaction['failed_reason'] = 'Insufficient funds'

        return {
            'status': current_status,
            'amount': transaction['amount'],
            'currency': transaction['currency'],
            'additional_data': {
                'cpay_receipt': transaction.get('cpay_receipt'),
                'payment_method': 'cpay_wallet',
                'completed_at': transaction.get('completed_at'),
                'failed_reason': transaction.get('failed_reason')
            }
        }

    def refund_payment(
            self,
            provider_transaction_id: str,
            amount: Optional[float] = None,
            reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process CPay refund (mock implementation)

        In a real implementation, this would:
        1. Make API call to CPay's refund endpoint
        2. Process the refund
        3. Return refund details

        Args:
            provider_transaction_id: CPay transaction ID
            amount: Refund amount (None for full refund)
            reason: Refund reason

        Returns:
            Dict containing refund details
        """
        transaction = self._mock_transactions.get(provider_transaction_id)

        if not transaction:
            raise RefundError(f'Transaction {provider_transaction_id} not found')

        if transaction['status'] != 'completed':
            raise RefundError('Can only refund completed transactions')

        # Generate mock refund ID
        refund_id = f'REF-{uuid.uuid4().hex[:12].upper()}'

        refund_amount = amount if amount else transaction['amount']

        # Store refund information
        if 'refunds' not in transaction:
            transaction['refunds'] = []

        transaction['refunds'].append({
            'refund_id': refund_id,
            'amount': refund_amount,
            'reason': reason,
            'status': 'completed',
            'created_at': datetime.utcnow().isoformat()
        })

        transaction['status'] = 'refunded'

        return {
            'refund_id': refund_id,
            'status': 'completed',
            'amount': refund_amount,
            'currency': transaction['currency'],
            'reason': reason,
            'additional_data': {
                'original_amount': transaction['amount'],
                'refund_method': 'original_payment_method',
                'estimated_arrival': '3-5 business days'
            }
        }

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify CPay webhook signature (mock implementation)

        In a real implementation, this would:
        1. Use CPay's webhook secret
        2. Calculate expected signature
        3. Compare with provided signature

        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers

        Returns:
            True if signature is valid
        """
        # Generate expected signature using HMAC-SHA256
        expected_signature = hmac.new(
            self.api_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures (constant-time comparison)
        return hmac.compare_digest(expected_signature, signature)

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process CPay webhook event (mock implementation)

        In a real implementation, this would:
        1. Parse CPay webhook payload
        2. Extract event type and data
        3. Return processed event

        Args:
            payload: Webhook event payload

        Returns:
            Dict containing processed event data
        """
        event_type = payload.get('event')
        data = payload.get('data', {})

        transaction_id = data.get('transaction_id')

        # Map CPay events to our system
        event_mapping = {
            'payment.success': 'payment.completed',
            'payment.failed': 'payment.failed',
            'payment.cancelled': 'payment.cancelled',
            'refund.completed': 'refund.completed',
            'refund.failed': 'refund.failed',
        }

        mapped_event = event_mapping.get(event_type, event_type)

        # Determine status
        status = 'pending'
        if 'success' in event_type or 'completed' in event_type:
            status = 'completed'
        elif 'failed' in event_type or 'cancelled' in event_type:
            status = 'failed'
        elif 'refund' in event_type:
            status = 'refunded'

        return {
            'transaction_id': transaction_id,
            'event_type': mapped_event,
            'status': status,
            'additional_data': {
                'cpay_event_id': payload.get('event_id'),
                'cpay_event_type': event_type,
                'amount': data.get('amount'),
                'currency': data.get('currency'),
                'payment_method': data.get('payment_method'),
                'data': data
            }
        }

    def _generate_checkout_token(self, transaction_id: str) -> str:
        """Generate mock checkout token"""
        return f'tok_{uuid.uuid4().hex[:24]}'

    def _get_expiry_time(self) -> str:
        """Get payment expiry time (15 minutes from now)"""
        from datetime import timedelta
        expiry = datetime.utcnow() + timedelta(minutes=15)
        return expiry.isoformat()

    @classmethod
    def simulate_webhook_callback(cls, transaction_id: str, status: str = 'completed') -> Dict[str, Any]:
        """
        Simulate a webhook callback for testing purposes

        Args:
            transaction_id: Transaction ID
            status: Desired status (completed, failed, cancelled)

        Returns:
            Mock webhook payload
        """
        event_map = {
            'completed': 'payment.success',
            'failed': 'payment.failed',
            'cancelled': 'payment.cancelled'
        }

        return {
            'event': event_map.get(status, 'payment.success'),
            'event_id': f'evt_{uuid.uuid4().hex[:16]}',
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'transaction_id': transaction_id,
                'amount': 1000.00,
                'currency': 'KES',
                'payment_method': 'cpay_wallet',
                'customer_reference': '+254700000000',
                'receipt_number': f'REC-{uuid.uuid4().hex[:10].upper()}',
                'timestamp': datetime.utcnow().isoformat()
            }
        }