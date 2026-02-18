import uuid
from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.utils.encryption import encrypt_value, decrypt_value


class ProviderConfig(db.Model):
    __tablename__ = 'provider_configs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)

    # Encrypted credentials
    _api_key = db.Column('api_key', db.String(500))
    _api_secret = db.Column('api_secret', db.String(500))
    _webhook_secret = db.Column('webhook_secret', db.String(500))

    # Additional configuration
    config = db.Column(JSONB)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    @property
    def api_key(self):
        if self._api_key:
            return decrypt_value(self._api_key)
        return None

    @api_key.setter
    def api_key(self, value):
        if value:
            self._api_key = encrypt_value(value)
        else:
            self._api_key = None

    @property
    def api_secret(self):
        if self._api_secret:
            return decrypt_value(self._api_secret)
        return None

    @api_secret.setter
    def api_secret(self, value):
        if value:
            self._api_secret = encrypt_value(value)
        else:
            self._api_secret = None

    @property
    def webhook_secret(self):
        if self._webhook_secret:
            return decrypt_value(self._webhook_secret)
        return None

    @webhook_secret.setter
    def webhook_secret(self, value):
        if value:
            self._webhook_secret = encrypt_value(value)
        else:
            self._webhook_secret = None

    def to_dict(self, include_secrets=False):
        data = {
            'id': str(self.id),
            'provider_name': self.provider_name,
            'is_active': self.is_active,
            'config': self.config,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

        if include_secrets:
            data['api_key'] = self.api_key
            data['api_secret'] = self.api_secret
            data['webhook_secret'] = self.webhook_secret

        return data

    def __repr__(self):
        return f'<ProviderConfig {self.provider_name}>'