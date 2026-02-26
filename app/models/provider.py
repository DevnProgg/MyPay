import uuid
from datetime import datetime

from celery.worker.strategy import default
from sqlalchemy.dialects.postgresql.base import UUID

from app.extensions import db

class ProviderTable(db.Model):
    __tablename__ = 'provider'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)

    #Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        data = {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        return data

    def __repr__(self):
        return '<Provider %r>' % self.name