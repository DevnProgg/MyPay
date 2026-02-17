"""
Webhook Validation Schemas
"""

from marshmallow import Schema, fields, validates, ValidationError


class WebhookEventSchema(Schema):
    """Webhook event schema for responses"""
    id = fields.UUID(dump_only=True)
    transaction_id = fields.UUID(dump_only=True)
    provider = fields.Str(dump_only=True)
    event_type = fields.Str(dump_only=True)
    payload = fields.Dict(dump_only=True)
    verified = fields.Bool(dump_only=True)
    processed = fields.Bool(dump_only=True)
    retry_count = fields.Int(dump_only=True)
    error_message = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    processed_at = fields.DateTime(dump_only=True)


class MPesaCallbackSchema(Schema):
    """M-Pesa callback validation schema"""
    Body = fields.Dict(required=True)

    @validates('Body')
    def validate_body(self, value):
        if 'stkCallback' not in value:
            raise ValidationError('Missing stkCallback in Body')


class StripeWebhookSchema(Schema):
    """Stripe webhook validation schema"""
    id = fields.Str(required=True)
    type = fields.Str(required=True)
    data = fields.Dict(required=True)
    created = fields.Int(required=True)


class CPayWebhookSchema(Schema):
    """CPay webhook validation schema"""
    event = fields.Str(required=True)
    event_id = fields.Str(required=True)
    timestamp = fields.Str(required=True)
    data = fields.Dict(required=True)