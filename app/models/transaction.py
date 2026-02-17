import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from enum import Enum


class TransactionStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = db.Column(db.String(255), unique=True, nullable=False, index=True)

    # Provider information
    provider = db.Column(db.String(50), nullable=False)
    provider_transaction_id = db.Column(db.String(255), index=True)
    provider_response = db.Column(JSONB)

    # Payment details
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='KES')
    status = db.Column(db.String(20), nullable=False, default=TransactionStatus.PENDING)

    # Customer information
    customer_id = db.Column(db.String(255), index=True)
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(255))
    customer_name = db.Column(db.String(255))

    # Payment method
    payment_method = db.Column(db.String(50))  # mpesa, card, etc.

    # Additional data
    metadata = db.Column(JSONB)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # Relationships
    audit_logs = db.relationship('AuditLog', backref='transaction', lazy='dynamic', cascade='all, delete-orphan')
    webhook_events = db.relationship('WebhookEvent', backref='transaction', lazy='dynamic',
                                     cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': str(self.id),
            'idempotency_key': self.idempotency_key,
            'provider': self.provider,
            'provider_transaction_id': self.provider_transaction_id,
            'amount': float(self.amount),
            'currency': self.currency,
            'status': self.status,
            'customer': {
                'id': self.customer_id,
                'phone': self.customer_phone,
                'email': self.customer_email,
                'name': self.customer_name
            },
            'payment_method': self.payment_method,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    def __repr__(self):
        return f'<Transaction {self.id} - {self.status}>'