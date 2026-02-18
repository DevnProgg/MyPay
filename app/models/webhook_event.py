import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class WebhookEvent(db.Model):
    __tablename__ = 'webhook_events'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey('transactions.id'), index=True)

    # Provider information
    provider = db.Column(db.String(50), nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False)

    # Webhook data
    payload = db.Column(JSONB, nullable=False)
    signature = db.Column(db.String(500))
    verified = db.Column(db.Boolean, default=False)

    # Processing status
    processed = db.Column(db.Boolean, default=False, index=True)
    retry_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    processed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': str(self.id),
            'transaction_id': str(self.transaction_id) if self.transaction_id else None,
            'provider': self.provider,
            'event_type': self.event_type,
            'verified': self.verified,
            'processed': self.processed,
            'retry_count': self.retry_count,
            'created_at': self.created_at.isoformat(),
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }

    def __repr__(self):
        return f'<WebhookEvent {self.id} - {self.provider}>'