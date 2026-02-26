import uuid

from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.extensions import db


class Merchant(db.Model):
    __tablename__ = 'merchant'

    id = db.Column(UUID(as_uuid = True), primary_key=True, default=uuid.uuid4)
    username =  db.Column(db.String(255), nullable=False, index=True, unique=True)
    password = db.Column(db.String(255), nullable=False)

    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    business_name = db.Column(db.String(255), nullable=False)
    business_category = db.Column(db.String(255), nullable=False)

    #encrypted credentials
    _api_key = db.Column("api_key", db.String(500), nullable=False)
    _api_secret = db.Column("api_secret", db.String(500), nullable=False)

