"""
Integration Tests for Payment Flow
End-to-end testing of payment processing
"""

import pytest
import json
from unittest.mock import patch, Mock


class TestPaymentFlowIntegration:
    """Integration tests for complete payment flows"""

    def test_complete_payment_flow_mpesa(self, client):
        """Test complete M-Pesa payment flow from initialization to completion"""

        with patch('app.providers.mpesa_provider.MPesaProvider.initialize_payment') as mock_init, \
                patch('app.providers.mpesa_provider.MPesaProvider.verify_payment') as mock_verify:
            # Mock M-Pesa responses
            mock_init.return_value = {
                'transaction_id': 'ws_CO_123456789',
                'merchant_request_id': 'merchant-123',
                'status': 'pending',
                'additional_data': {
                    'customer_message': 'Success. Request accepted for processing'
                }
            }

            mock_verify.return_value = {
                'status': 'completed',
                'result_code': '0',
                'result_desc': 'The service request is processed successfully.'
            }

            # Step 1: Initialize payment
            init_response = client.post(
                '/api/v1/payments/initialize',
                headers={
                    'Content-Type': 'application/json',
                    'Idempotency-Key': 'test-flow-123'
                },
                data=json.dumps({
                    'provider': 'mpesa',
                    'amount': 1000.00,
                    'currency': 'KES',
                    'customer': {
                        'phone': '+254700000000',
                        'email': 'test@example.com',
                        'name': 'Test User'
                    },
                    'metadata': {
                        'order_id': 'ORD-123'
                    }
                })
            )

            assert init_response.status_code == 201
            data = json.loads(init_response.data)
            assert data['success'] is True
            assert data['data']['status'] == 'processing'

            transaction_id = data['data']['id']

            # Step 2: Verify payment
            verify_response = client.post(
                f'/api/v1/payments/{transaction_id}/verify'
            )

            assert verify_response.status_code == 200
            verify_data = json.loads(verify_response.data)
            assert verify_data['success'] is True
            assert verify_data['data']['status'] == 'completed'

            # Step 3: Get payment details
            get_response = client.get(
                f'/api/v1/payments/{transaction_id}'
            )

            assert get_response.status_code == 200
            get_data = json.loads(get_response.data)
            assert get_data['success'] is True
            assert get_data['data']['status'] == 'completed'

    def test_webhook_processing_flow(self, client, session):
        """Test webhook processing flow"""

        with patch('app.providers.mpesa_provider.MPesaProvider.initialize_payment') as mock_init, \
                patch('app.providers.mpesa_provider.MPesaProvider.verify_webhook_signature') as mock_verify_sig, \
                patch('app.providers.mpesa_provider.MPesaProvider.handle_webhook') as mock_handle:
            # Initialize a payment first
            mock_init.return_value = {
                'transaction_id': 'ws_CO_123456789',
                'status': 'pending'
            }

            init_response = client.post(
                '/api/v1/payments/initialize',
                headers={
                    'Content-Type': 'application/json',
                    'Idempotency-Key': 'webhook-flow-123'
                },
                data=json.dumps({
                    'provider': 'mpesa',
                    'amount': 1000.00,
                    'currency': 'KES',
                    'customer': {
                        'phone': '+254700000000',
                        'email': 'test@example.com'
                    }
                })
            )

            assert init_response.status_code == 201

            # Mock webhook verification and handling
            mock_verify_sig.return_value = True
            mock_handle.return_value = {
                'transaction_id': 'ws_CO_123456789',
                'event_type': 'payment.completed',
                'status': 'completed',
                'additional_data': {
                    'mpesa_receipt_number': 'ABC123XYZ',
                    'amount': 1000.00
                }
            }

            # Send webhook
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

            webhook_response = client.post(
                '/api/v1/webhooks/mpesa',
                headers={
                    'Content-Type': 'application/json'
                },
                data=json.dumps(webhook_payload)
            )

            assert webhook_response.status_code == 200
            webhook_data = json.loads(webhook_response.data)
            assert webhook_data['success'] is True

    def test_refund_flow(self, client):
        """Test complete refund flow"""

        with patch('app.providers.stripe_provider.StripeProvider.initialize_payment') as mock_init, \
                patch('app.providers.stripe_provider.StripeProvider.verify_payment') as mock_verify, \
                patch('app.providers.stripe_provider.StripeProvider.refund_payment') as mock_refund:
            # Mock Stripe responses
            mock_init.return_value = {
                'transaction_id': 'pi_123456789',
                'client_secret': 'pi_123_secret_456',
                'status': 'processing'
            }

            mock_verify.return_value = {
                'status': 'completed',
                'amount': 100.00,
                'currency': 'USD'
            }

            mock_refund.return_value = {
                'refund_id': 're_123456789',
                'status': 'completed',
                'amount': 100.00,
                'currency': 'USD'
            }

            # Step 1: Initialize payment
            init_response = client.post(
                '/api/v1/payments/initialize',
                headers={
                    'Content-Type': 'application/json',
                    'Idempotency-Key': 'refund-flow-123'
                },
                data=json.dumps({
                    'provider': 'stripe',
                    'amount': 100.00,
                    'currency': 'USD',
                    'customer': {
                        'email': 'test@example.com',
                        'name': 'Test User'
                    }
                })
            )

            assert init_response.status_code == 201
            transaction_id = json.loads(init_response.data)['data']['id']

            # Step 2: Verify payment completed
            client.post(f'/api/v1/payments/{transaction_id}/verify')

            # Step 3: Process refund
            refund_response = client.post(
                f'/api/v1/payments/{transaction_id}/refund',
                headers={
                    'Content-Type': 'application/json',
                    'Idempotency-Key': 'refund-request-123'
                },
                data=json.dumps({
                    'amount': 100.00,
                    'reason': 'Customer request'
                })
            )

            assert refund_response.status_code == 200
            refund_data = json.loads(refund_response.data)
            assert refund_data['success'] is True
            assert refund_data['data']['status'] == 'refunded'

    def test_list_transactions_flow(self, client):
        """Test listing transactions with various filters"""

        with patch('app.providers.get_provider') as mock_get_provider:
            mock_provider = Mock()
            mock_provider.initialize_payment.return_value = {
                'transaction_id': 'test-123',
                'status': 'processing'
            }
            mock_get_provider.return_value = mock_provider

            # Create multiple transactions
            for i in range(5):
                client.post(
                    '/api/v1/payments/initialize',
                    headers={
                        'Content-Type': 'application/json',
                        'Idempotency-Key': f'list-flow-{i}'
                    },
                    data=json.dumps({
                        'provider': 'mpesa',
                        'amount': 1000.00 * (i + 1),
                        'currency': 'KES',
                        'customer': {
                            'phone': '+254700000000'
                        }
                    })
                )

            # Test listing all transactions
            list_response = client.get('/api/v1/payments')
            assert list_response.status_code == 200
            list_data = json.loads(list_response.data)
            assert list_data['success'] is True
            assert len(list_data['data']['items']) == 5

            # Test filtering by provider
            filter_response = client.get('/api/v1/payments?provider=mpesa')
            assert filter_response.status_code == 200
            filter_data = json.loads(filter_response.data)
            assert filter_data['success'] is True

            # Test pagination
            page_response = client.get('/api/v1/payments?page=1&per_page=2')
            assert page_response.status_code == 200
            page_data = json.loads(page_response.data)
            assert len(page_data['data']['items']) == 2
            assert page_data['data']['pagination']['pages'] >= 3

    def test_idempotency_enforcement(self, client):
        """Test that idempotency is properly enforced"""

        with patch('app.providers.get_provider') as mock_get_provider:
            mock_provider = Mock()
            mock_provider.initialize_payment.return_value = {
                'transaction_id': 'test-123',
                'status': 'processing'
            }
            mock_get_provider.return_value = mock_provider

            idempotency_key = 'idempotency-test-123'
            payload = {
                'provider': 'mpesa',
                'amount': 1000.00,
                'currency': 'KES',
                'customer': {
                    'phone': '+254700000000'
                }
            }

            # First request
            response1 = client.post(
                '/api/v1/payments/initialize',
                headers={
                    'Content-Type': 'application/json',
                    'Idempotency-Key': idempotency_key
                },
                data=json.dumps(payload)
            )

            assert response1.status_code == 201
            data1 = json.loads(response1.data)
            transaction_id1 = data1['data']['id']

            # Second request with same idempotency key
            response2 = client.post(
                '/api/v1/payments/initialize',
                headers={
                    'Content-Type': 'application/json',
                    'Idempotency-Key': idempotency_key
                },
                data=json.dumps(payload)
            )

            assert response2.status_code == 200  # Should return cached response
            data2 = json.loads(response2.data)
            transaction_id2 = data2['data']['id']

            # Should be the same transaction
            assert transaction_id1 == transaction_id2

            # Provider should only be called once
            assert mock_provider.initialize_payment.call_count == 1

    def test_validation_errors(self, client):
        """Test API validation error handling"""

        # Missing required fields
        response = client.post(
            '/api/v1/payments/initialize',
            headers={
                'Content-Type': 'application/json',
                'Idempotency-Key': 'validation-test-1'
            },
            data=json.dumps({
                'provider': 'mpesa',
                'amount': 1000.00
                # Missing currency and customer
            })
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data

        # Invalid amount
        response = client.post(
            '/api/v1/payments/initialize',
            headers={
                'Content-Type': 'application/json',
                'Idempotency-Key': 'validation-test-2'
            },
            data=json.dumps({
                'provider': 'mpesa',
                'amount': -100.00,  # Negative amount
                'currency': 'KES',
                'customer': {'phone': '+254700000000'}
            })
        )

        assert response.status_code == 400

        # Missing idempotency key
        response = client.post(
            '/api/v1/payments/initialize',
            headers={
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'provider': 'mpesa',
                'amount': 1000.00,
                'currency': 'KES',
                'customer': {'phone': '+254700000000'}
            })
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Idempotency-Key' in data['error']