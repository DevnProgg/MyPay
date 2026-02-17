"""
Integration Tests for Webhook Processing
"""

import pytest
import json
from unittest.mock import patch, Mock
from app.models import Transaction, WebhookEvent


class TestWebhookIntegration:
    """Integration tests for webhook processing"""

    def test_mpesa_webhook_processing(self, client, session):
        """Test M-Pesa webhook end-to-end processing"""

        # Step 1: Create a pending transaction
        transaction = Transaction(
            idempotency_key='webhook-test-1',
            provider='mpesa',
            provider_transaction_id='ws_CO_123456789',
            amount=1000.00,
            currency='KES',
            customer_phone='+254700000000',
            status='processing'
        )
        session.add(transaction)
        session.commit()

        # Step 2: Simulate M-Pesa callback
        with patch('app.providers.mpesa_provider.MPesaProvider.verify_webhook_signature') as mock_verify, \
                patch('app.providers.mpesa_provider.MPesaProvider.handle_webhook') as mock_handle:
            mock_verify.return_value = True
            mock_handle.return_value = {
                'transaction_id': 'ws_CO_123456789',
                'event_type': 'payment.completed',
                'status': 'completed',
                'additional_data': {
                    'mpesa_receipt_number': 'ABC123XYZ',
                    'amount': 1000.00
                }
            }

            webhook_payload = {
                'Body': {
                    'stkCallback': {
                        'MerchantRequestID': 'merchant-123',
                        'CheckoutRequestID': 'ws_CO_123456789',
                        'ResultCode': 0,
                        'ResultDesc': 'The service request is processed successfully.',
                        'CallbackMetadata': {
                            'Item': [
                                {'Name': 'Amount', 'Value': 1000},
                                {'Name': 'MpesaReceiptNumber', 'Value': 'ABC123XYZ'},
                                {'Name': 'PhoneNumber', 'Value': 254700000000}
                            ]
                        }
                    }
                }
            }

            response = client.post(
                '/api/v1/webhooks/mpesa',
                headers={'Content-Type': 'application/json'},
                data=json.dumps(webhook_payload)
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True

            # Verify transaction was updated
            updated_transaction = Transaction.query.filter_by(
                provider_transaction_id='ws_CO_123456789'
            ).first()
            assert updated_transaction.status == 'completed'

    def test_stripe_webhook_processing(self, client, session):
        """Test Stripe webhook processing"""

        # Step 1: Create a pending transaction
        transaction = Transaction(
            idempotency_key='stripe-webhook-test',
            provider='stripe',
            provider_transaction_id='pi_123456789',
            amount=100.00,
            currency='USD',
            customer_email='test@example.com',
            status='processing'
        )
        session.add(transaction)
        session.commit()

        # Step 2: Simulate Stripe webhook
        with patch('app.providers.stripe_provider.StripeProvider.verify_webhook_signature') as mock_verify, \
                patch('app.providers.stripe_provider.StripeProvider.handle_webhook') as mock_handle:
            mock_verify.return_value = True
            mock_handle.return_value = {
                'transaction_id': 'pi_123456789',
                'event_type': 'payment.completed',
                'status': 'completed',
                'additional_data': {
                    'stripe_event_id': 'evt_123',
                    'amount': 100.00,
                    'currency': 'USD'
                }
            }

            webhook_payload = {
                'id': 'evt_123',
                'type': 'payment_intent.succeeded',
                'created': 1234567890,
                'data': {
                    'object': {
                        'id': 'pi_123456789',
                        'object': 'payment_intent',
                        'amount': 10000,
                        'currency': 'usd',
                        'status': 'succeeded'
                    }
                }
            }

            response = client.post(
                '/api/v1/webhooks/stripe',
                headers={
                    'Content-Type': 'application/json',
                    'Stripe-Signature': 'mock_signature'
                },
                data=json.dumps(webhook_payload)
            )

            assert response.status_code == 200

            # Verify transaction was updated
            updated_transaction = Transaction.query.filter_by(
                provider_transaction_id='pi_123456789'
            ).first()
            assert updated_transaction.status == 'completed'

    def test_webhook_retry_mechanism(self, client, session):
        """Test webhook retry on failure"""

        # Create a webhook event that will fail
        transaction = Transaction(
            idempotency_key='retry-test',
            provider='mpesa',
            provider_transaction_id='ws_CO_RETRY',
            amount=1000.00,
            currency='KES',
            status='processing'
        )
        session.add(transaction)
        session.commit()

        with patch('app.providers.mpesa_provider.MPesaProvider.verify_webhook_signature') as mock_verify, \
                patch('app.providers.mpesa_provider.MPesaProvider.handle_webhook') as mock_handle:
            mock_verify.return_value = True

            # First attempt fails
            mock_handle.side_effect = Exception('Processing error')

            webhook_payload = {
                'Body': {
                    'stkCallback': {
                        'CheckoutRequestID': 'ws_CO_RETRY',
                        'ResultCode': 0
                    }
                }
            }

            response = client.post(
                '/api/v1/webhooks/mpesa',
                headers={'Content-Type': 'application/json'},
                data=json.dumps(webhook_payload)
            )

            # Should still return 200 to prevent provider retries
            assert response.status_code == 200

            # Check webhook event was created with error
            webhook_event = WebhookEvent.query.filter_by(
                provider='mpesa'
            ).first()
            assert webhook_event is not None
            assert webhook_event.processed is False
            assert webhook_event.retry_count > 0

    def test_webhook_signature_verification_failure(self, client, session):
        """Test webhook with invalid signature is rejected"""

        with patch('app.providers.stripe_provider.StripeProvider.verify_webhook_signature') as mock_verify:
            mock_verify.return_value = False  # Invalid signature

            webhook_payload = {
                'id': 'evt_123',
                'type': 'payment_intent.succeeded',
                'data': {'object': {}}
            }

            response = client.post(
                '/api/v1/webhooks/stripe',
                headers={
                    'Content-Type': 'application/json',
                    'Stripe-Signature': 'invalid_signature'
                },
                data=json.dumps(webhook_payload)
            )

            # Should still return 200 but not process
            assert response.status_code == 200

            # Verify webhook event marked as not verified
            webhook_event = WebhookEvent.query.filter_by(
                provider='stripe'
            ).first()
            assert webhook_event is not None
            assert webhook_event.verified is False

    def test_webhook_list_endpoint(self, client, session, sample_webhook_event):
        """Test listing webhook events"""

        response = client.get('/api/v1/webhooks/events')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'items' in data['data']
        assert len(data['data']['items']) > 0

    def test_webhook_retry_endpoint(self, client, session, sample_webhook_event):
        """Test manual webhook retry endpoint"""

        with patch('app.services.webhook_service.WebhookService.process_webhook') as mock_process:
            mock_process.return_value = True

            response = client.post(
                f'/api/v1/webhooks/events/{sample_webhook_event.id}/retry'
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True

    def test_webhook_statistics_endpoint(self, client, session):
        """Test webhook statistics endpoint"""

        # Create some webhook events
        for i in range(5):
            event = WebhookEvent(
                provider='mpesa',
                event_type='payment.callback',
                payload={'test': 'data'},
                verified=True,
                processed=(i % 2 == 0)  # Half processed
            )
            session.add(event)
        session.commit()

        response = client.get('/api/v1/webhooks/statistics')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'total' in data['data']
        assert 'processed' in data['data']
        assert 'by_provider' in data['data']

    def test_webhook_dead_letter_queue(self, client, session):
        """Test dead letter queue endpoint"""

        # Create failed webhook events
        for i in range(3):
            event = WebhookEvent(
                provider='mpesa',
                event_type='payment.callback',
                payload={'test': 'data'},
                verified=True,
                processed=False,
                retry_count=6  # Exceeded max retries
            )
            session.add(event)
        session.commit()

        response = client.get('/api/v1/webhooks/dead-letter-queue')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['count'] == 3

    def test_cpay_webhook_processing(self, client, session):
        """Test CPay webhook processing"""

        transaction = Transaction(
            idempotency_key='cpay-webhook-test',
            provider='cpay',
            provider_transaction_id='CPAY-123456',
            amount=1000.00,
            currency='KES',
            status='processing'
        )
        session.add(transaction)
        session.commit()

        with patch('app.providers.cpay_provider.CPayProvider.verify_webhook_signature') as mock_verify, \
                patch('app.providers.cpay_provider.CPayProvider.handle_webhook') as mock_handle:
            mock_verify.return_value = True
            mock_handle.return_value = {
                'transaction_id': 'CPAY-123456',
                'event_type': 'payment.completed',
                'status': 'completed',
                'additional_data': {
                    'cpay_event_id': 'evt_123',
                    'amount': 1000.00
                }
            }

            webhook_payload = {
                'event': 'payment.success',
                'event_id': 'evt_123',
                'timestamp': '2024-01-01T12:00:00Z',
                'data': {
                    'transaction_id': 'CPAY-123456',
                    'amount': 1000.00,
                    'currency': 'KES'
                }
            }

            response = client.post(
                '/api/v1/webhooks/cpay',
                headers={
                    'Content-Type': 'application/json',
                    'X-CPay-Signature': 'mock_signature'
                },
                data=json.dumps(webhook_payload)
            )

            assert response.status_code == 200

            # Verify transaction updated
            updated_transaction = Transaction.query.filter_by(
                provider_transaction_id='CPAY-123456'
            ).first()
            assert updated_transaction.status == 'completed'