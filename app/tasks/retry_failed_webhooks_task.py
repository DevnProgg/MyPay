from datetime import datetime

from app import celery_app

from app.models import WebhookEvent
from app.services.webhook_service import WebhookService


@celery_app.task(name='retry_failed_webhook_task')
def retry_failed_webhooks(api_key : str):
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

            time_since_creation = (datetime.now() - webhook.created_at).total_seconds()

            if time_since_creation >= retry_interval:
                try:
                    success = WebhookService.process_webhook(webhook.id)
                    if success:
                        processed_count += 1
                except Exception as e:
                    import logging
                    logging.error(f'Retry failed for webhook {webhook.id}: {str(e)}')

        return processed_count