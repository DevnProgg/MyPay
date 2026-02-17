"""
Webhook Service
Handles receiving, verifying, and processing webhooks from payment providers
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import time

from app.extensions import db
from app.models import WebhookEvent, Transaction, TransactionStatus
from app.providers import get_provider
from app.services.audit_service import AuditService
from app.websockets.events import emit_transaction_update


class WebhookService:
    """Service for handling provider webhooks"""

    # Maximum retry attempts for failed webhooks
    MAX_RETRY_ATTEMPTS = 5

    # Retry schedule in seconds: 1min, 5min, 15min, 1hr, 6hr
    RETRY_SCHEDULE = [60, 300, 900, 3600, 21600]

    @staticmethod
    def receive_webhook(
            provider: str,
            payload: Dict[str, Any],
            signature: Optional[str] = None,
            raw_payload: Optional[bytes] = None
    ) -> WebhookEvent:
        """
        Receive and store webhook event

        Args:
            provider: Payment provider name
            payload: Webhook payload (parsed JSON)
            signature: Webhook signature from headers
            raw_payload: Raw payload bytes for signature verification

        Returns:
            Created WebhookEvent object
        """
        # Create webhook event record
        webhook_event = WebhookEvent(
            provider=provider,
            event_type=payload.get('event', payload.get('type', 'unknown')),
            payload=payload,
            signature=signature,
            verified=False,
            processed=False
        )

        db.session.add(webhook_event)
        db.session.commit()

        # Verify signature if provided
        if signature and raw_payload:
            try:
                provider_instance = get_provider(provider)
                is_valid = provider_instance.verify_webhook_signature(
                    raw_payload,
                    signature
                )

                webhook_event.verified = is_valid
                db.session.commit()

            except Exception as e:
                webhook_event.error_message = f'Signature verification failed: {str(e)}'
                db.session.commit()
        else:
            # No signature verification available
            webhook_event.verified = True
            db.session.commit()

        return webhook_event

    @staticmethod
    def process_webhook(webhook_event_id: uuid.UUID) -> bool:
        """
        Process a webhook event

        Args:
            webhook_event_id: UUID of the webhook event

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
            provider_instance = get_provider(webhook_event.provider)

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
                transaction.completed_at = datetime.utcnow()
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
            webhook_event.processed_at = datetime.utcnow()

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

            # Emit WebSocket event
            emit_transaction_update(transaction, event_type)

            return True

        except Exception as e:
            webhook_event.error_message = str(e)
            webhook_event.retry_count += 1
            db.session.commit()

            # Log error
            import logging
            logging.error(f'Webhook processing failed: {str(e)}')

            return False

    @staticmethod
    def retry_failed_webhooks():
        """
        Retry processing of failed webhooks based on retry schedule

        This should be called periodically (e.g., by a background job)
        """
        # Get failed webhooks that are due for retry
        failed_webhooks = WebhookEvent.query.filter(
            WebhookEvent.processed == False,
            WebhookEvent.retry_count < WebhookService.MAX_RETRY_ATTEMPTS
        ).all()

        processed_count = 0

        for webhook in failed_webhooks:
            # Check if enough time has passed for next retry
            if webhook.retry_count >= len(WebhookService.RETRY_SCHEDULE):
                # Use last retry interval
                retry_interval = WebhookService.RETRY_SCHEDULE[-1]
            else:
                retry_interval = WebhookService.RETRY_SCHEDULE[webhook.retry_count]

            time_since_creation = (datetime.utcnow() - webhook.created_at).total_seconds()

            if time_since_creation >= retry_interval:
                try:
                    success = WebhookService.process_webhook(webhook.id)
                    if success:
                        processed_count += 1
                except Exception as e:
                    import logging
                    logging.error(f'Retry failed for webhook {webhook.id}: {str(e)}')

        return processed_count

    @staticmethod
    def get_webhook_events(
            provider: Optional[str] = None,
            processed: Optional[bool] = None,
            verified: Optional[bool] = None,
            transaction_id: Optional[uuid.UUID] = None,
            page: int = 1,
            per_page: int = 50
    ):
        """
        Get webhook events with filters

        Args:
            provider: Filter by provider
            processed: Filter by processed status
            verified: Filter by verification status
            transaction_id: Filter by transaction ID
            page: Page number
            per_page: Items per page

        Returns:
            Paginated webhook events
        """
        query = WebhookEvent.query

        if provider:
            query = query.filter_by(provider=provider)

        if processed is not None:
            query = query.filter_by(processed=processed)

        if verified is not None:
            query = query.filter_by(verified=verified)

        if transaction_id:
            query = query.filter_by(transaction_id=transaction_id)

        return query.order_by(WebhookEvent.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

    @staticmethod
    def get_dead_letter_queue():
        """
        Get webhooks that have exceeded retry attempts

        Returns:
            List of webhook events in dead letter queue
        """
        return WebhookEvent.query.filter(
            WebhookEvent.processed == False,
            WebhookEvent.retry_count >= WebhookService.MAX_RETRY_ATTEMPTS
        ).all()

    @staticmethod
    def mark_webhook_as_processed(webhook_event_id: uuid.UUID):
        """
        Manually mark a webhook as processed

        Args:
            webhook_event_id: UUID of the webhook event
        """
        webhook_event = WebhookEvent.query.get(webhook_event_id)

        if webhook_event:
            webhook_event.processed = True
            webhook_event.processed_at = datetime.utcnow()
            db.session.commit()

    @staticmethod
    def get_webhook_statistics(
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get webhook statistics

        Args:
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            Dict containing webhook statistics
        """
        from sqlalchemy import func

        query = WebhookEvent.query

        if start_date:
            query = query.filter(WebhookEvent.created_at >= start_date)

        if end_date:
            query = query.filter(WebhookEvent.created_at <= end_date)

        total = query.count()
        processed = query.filter(WebhookEvent.processed == True).count()
        failed = query.filter(
            WebhookEvent.processed == False,
            WebhookEvent.retry_count >= WebhookService.MAX_RETRY_ATTEMPTS
        ).count()
        pending = total - processed - failed

        # Get counts by provider
        provider_stats = db.session.query(
            WebhookEvent.provider,
            func.count(WebhookEvent.id).label('count')
        )

        if start_date:
            provider_stats = provider_stats.filter(WebhookEvent.created_at >= start_date)

        if end_date:
            provider_stats = provider_stats.filter(WebhookEvent.created_at <= end_date)

        provider_counts = {
            provider: count
            for provider, count in provider_stats.group_by(WebhookEvent.provider).all()
        }

        return {
            'total': total,
            'processed': processed,
            'pending': pending,
            'failed': failed,
            'by_provider': provider_counts,
            'success_rate': (processed / total * 100) if total > 0 else 0
        }