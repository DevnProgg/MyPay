from typing import Dict, Any, Optional

from app import celery_app
from app.models import WebhookEvent
from app.extensions import db
from app.providers import get_provider

@celery_app.task(name='receive_webhook_task')
def receive_webhook(
        provider: str,
        payload: Dict[str, Any],
        signature: Optional[str] = None,
        raw_payload: Optional[bytes] = None,
        api_key : Optional[str] = None
) -> WebhookEvent:
    """
    Receive and store webhook event

    Args:
        provider: Payment provider name
        payload: Webhook payload (parsed JSON)
        signature: Webhook signature from headers
        raw_payload: Raw payload bytes for signature verification
        api_key: Payment API key

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
            provider_instance = get_provider(provider, api_key)
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