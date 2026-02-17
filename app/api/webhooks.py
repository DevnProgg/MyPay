"""
Webhook API Endpoints
Handles incoming webhooks from payment providers
"""

from flask import Blueprint, request, jsonify
import json

from app.services.webhook_service import WebhookService
from app.utils.logger import get_logger

webhooks_bp = Blueprint('webhooks', __name__)
logger = get_logger(__name__)


@webhooks_bp.route('/<provider>', methods=['POST'])
def receive_webhook(provider):
    """
    Receive webhook from payment provider

    Path Parameters:
        provider: Payment provider name (mpesa, stripe, cpay)

    Headers:
        - Stripe-Signature (for Stripe)
        - X-CPay-Signature (for CPay)
        - Various headers depending on provider

    Body:
        Provider-specific webhook payload
    """
    try:
        # Get raw payload for signature verification
        raw_payload = request.get_data()

        # Parse JSON payload
        try:
            payload = request.get_json()
        except Exception as e:
            logger.error(f'Failed to parse webhook payload: {str(e)}')
            return jsonify({
                'success': False,
                'error': 'Invalid JSON payload'
            }), 400

        # Get signature from headers (provider-specific)
        signature = None
        if provider == 'stripe':
            signature = request.headers.get('Stripe-Signature')
        elif provider == 'mpesa':
            # M-Pesa doesn't use signatures, but we can verify source IP
            signature = None
        elif provider == 'cpay':
            signature = request.headers.get('X-CPay-Signature')

        # Log webhook receipt
        logger.info(f'Received webhook from {provider}: {payload.get("event", "unknown")}')

        # Store webhook event
        webhook_event = WebhookService.receive_webhook(
            provider=provider,
            payload=payload,
            signature=signature,
            raw_payload=raw_payload
        )

        # Process webhook asynchronously (in production, use Celery)
        # For now, process synchronously
        success = WebhookService.process_webhook(webhook_event.id)

        if success:
            return jsonify({
                'success': True,
                'webhook_event_id': str(webhook_event.id),
                'message': 'Webhook processed successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'webhook_event_id': str(webhook_event.id),
                'message': 'Webhook processing failed, will retry'
            }), 200  # Still return 200 to prevent provider retries

    except Exception as e:
        logger.error(f'Webhook error: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@webhooks_bp.route('/events', methods=['GET'])
def list_webhook_events():
    """
    List webhook events (admin endpoint)

    Query Parameters:
        - provider: Filter by provider
        - processed: Filter by processed status (true/false)
        - verified: Filter by verification status (true/false)
        - page: Page number (default: 1)
        - per_page: Items per page (default: 50)
    """
    try:
        provider = request.args.get('provider')
        processed = request.args.get('processed')
        verified = request.args.get('verified')
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)

        # Convert string booleans
        if processed is not None:
            processed = processed.lower() == 'true'

        if verified is not None:
            verified = verified.lower() == 'true'

        pagination = WebhookService.get_webhook_events(
            provider=provider,
            processed=processed,
            verified=verified,
            page=page,
            per_page=per_page
        )

        return jsonify({
            'success': True,
            'data': {
                'items': [event.to_dict() for event in pagination.items],
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


@webhooks_bp.route('/events/<uuid:event_id>/retry', methods=['POST'])
def retry_webhook(event_id):
    """
    Manually retry processing a webhook event

    Path Parameters:
        event_id: Webhook event UUID
    """
    try:
        success = WebhookService.process_webhook(event_id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Webhook processed successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Webhook processing failed'
            }), 400

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


@webhooks_bp.route('/dead-letter-queue', methods=['GET'])
def get_dead_letter_queue():
    """
    Get webhooks in dead letter queue (exceeded retry attempts)
    """
    try:
        failed_webhooks = WebhookService.get_dead_letter_queue()

        return jsonify({
            'success': True,
            'data': {
                'count': len(failed_webhooks),
                'items': [webhook.to_dict() for webhook in failed_webhooks]
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@webhooks_bp.route('/statistics', methods=['GET'])
def get_webhook_statistics():
    """
    Get webhook processing statistics

    Query Parameters:
        - start_date: Start date (ISO format)
        - end_date: End date (ISO format)
    """
    try:
        from datetime import datetime

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if start_date:
            start_date = datetime.fromisoformat(start_date)

        if end_date:
            end_date = datetime.fromisoformat(end_date)

        stats = WebhookService.get_webhook_statistics(
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            'success': True,
            'data': stats
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500