"""
Integration Tests for Webhook Processing
"""

import pytest
import json
from unittest.mock import patch, Mock
from app.models import Transaction, WebhookEvent


class TestWebhookIntegration:
    """Integration tests for webhook processing"""

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
