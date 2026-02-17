import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey('transactions.id'), nullable=False, index=True)

    # Event details
    event_type = db.Column(db.String(100), nullable=False)
    event_data = db.Column(JSONB)

    # Request context
    user_id = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))

    # Timestamp
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': str(self.id),
            'transaction_id': str(self.transaction_id),
            'event_type': self.event_type,
            'event_data': self.event_data,
            'user_id': self.user_id,
            'ip_address': self.ip_address,
            'timestamp': self.timestamp.isoformat()
        }

    def __repr__(self):
        return f'<AuditLog {self.id} - {self.event_type}>'