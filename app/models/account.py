import uuid
from datetime import datetime

from django.contrib.sitemaps.views import index
from sqlalchemy.dialects.postgresql.base import UUID

from app.extensions import db


class Account(db.Model):
    __tablename__ = 'account'

    id = db.Column(UUID(as_uuid = True), primary_key=True, default=uuid.uuid4)
    merchant_id = db.Column(UUID(as_uuid = True), db.ForeignKey('merchant.id'))

    username = db.Column(db.String(255), index=True, unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    #Encrypted Creds
    api_key = db.Column(db.String(255), nullable=True, index=True)

    #Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self) -> dict:
        data = {
            'id': self.id,
            'merchant': self.merchant_id if self.merchant_id else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'api_key' : self.api_key
        }

        return data