import datetime
import uuid

from app import celery_app
from app.models import WebhookEvent, Transaction, TransactionStatus
from app.providers import get_provider
from app.services.audit_service import AuditService
from app.extensions import db

@celery_app.task(name='process_webhook_task')
def process_webhook(webhook_event_id: uuid.UUID, api_key: str) -> bool:
    """
    Process a webhook event

    Args:
        webhook_event_id: UUID of the webhook event
        api_key (str): API key

    Returns:
        True if processing successful, False otherwise
    """
    webhook_event = WebhookEvent.query.get(webhook_event_id)

    if not webhook_event:
        raise ValueError(f'Webhook event {webhook_event_id} not found')

    if webhook_event.processed:
        # Already processed
        return True

    if not webhook_event.verified:
        webhook_event.error_message = 'Webhook signature not verified'
        webhook_event.retry_count += 1
        db.session.commit()
        return False

    try:
        # Get provider instance
        provider_instance = get_provider(webhook_event.provider, api_key)

        # Handle webhook with provider
        result = provider_instance.handle_webhook(webhook_event.payload)

        # Extract transaction information
        provider_transaction_id = result.get('transaction_id')
        event_type = result.get('event_type')
        status = result.get('status')
        additional_data = result.get('additional_data', {})

        # Find transaction in our database
        transaction = Transaction.query.filter_by(
            provider_transaction_id=provider_transaction_id
        ).first()

        if not transaction:
            webhook_event.error_message = f'Transaction not found: {provider_transaction_id}'
            webhook_event.retry_count += 1
            db.session.commit()
            return False

        # Link webhook to transaction
        webhook_event.transaction_id = transaction.id

        # Update transaction status
        old_status = transaction.status

        if status == 'completed':
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.datetime.now()
        elif status == 'failed':
            transaction.status = TransactionStatus.FAILED
        elif status == 'refunded':
            transaction.status = TransactionStatus.REFUNDED

        # Update provider response
        if transaction.provider_response:
            transaction.provider_response['webhook_data'] = additional_data
        else:
            transaction.provider_response = {'webhook_data': additional_data}

        # Mark webhook as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.now()

        db.session.commit()

        # Log audit event
        AuditService.log_event(
            transaction_id=transaction.id,
            event_type=event_type,
            event_data={
                'old_status': old_status,
                'new_status': transaction.status,
                'webhook_event_id': str(webhook_event.id),
                'webhook_data': additional_data
            }
        )

        # s

        return True

    except Exception as e:
        webhook_event.error_message = str(e)
        webhook_event.retry_count += 1
        db.session.commit()

        # Log error
        import logging
        logging.error(f'Webhook processing failed: {str(e)}')

        return False