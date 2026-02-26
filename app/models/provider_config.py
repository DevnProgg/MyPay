import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB


class ProviderConfig(db.Model):
    __tablename__ = 'provider_merchant_config'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=False)

    # configuration
    config = db.Column(JSONB)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self, include_secrets=False):
        data = {
            'id': str(self.id),
            'provider_id': self.provider_id,
            'is_active': self.is_active,
            'config': self.config,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        return data

    def __repr__(self):
        return f'<ProviderConfig {self.provider_id}>'