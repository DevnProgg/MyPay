import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class Merchant(db.Model):
    __tablename__ = 'merchant'

    id = db.Column(UUID(as_uuid = True), primary_key=True, default=uuid.uuid4)

    #Personal Information
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    number = db.Column(db.String(255), nullable=False)
    business_name = db.Column(db.String(255), nullable=False)
    business_category = db.Column(db.String(255), nullable=False)

    #Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "number": self.number,
            "business_name": self.business_name,
            "business_category": self.business_category,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        return data