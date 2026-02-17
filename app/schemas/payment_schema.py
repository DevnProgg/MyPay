from marshmallow import Schema, fields, validates, ValidationError


class CustomerSchema(Schema):
    """Customer data schema"""
    id = fields.Str(required=False)
    phone = fields.Str(required=True)
    email = fields.Email(required=False)
    name = fields.Str(required=False)


class InitializePaymentSchema(Schema):
    """Payment initialization schema"""
    provider = fields.Str(required=True)
    amount = fields.Decimal(required=True, places=2)
    currency = fields.Str(required=True)
    customer = fields.Nested(CustomerSchema, required=True)
    metadata = fields.Dict(required=False)

    @validates('amount')
    def validate_amount(self, value):
        if value <= 0:
            raise ValidationError('Amount must be greater than 0')

    @validates('provider')
    def validate_provider(self, value):
        allowed_providers = ['mpesa', 'stripe', 'visa', 'cpay']
        if value.lower() not in allowed_providers:
            raise ValidationError(f'Provider must be one of: {", ".join(allowed_providers)}')


class RefundPaymentSchema(Schema):
    """Refund payment schema"""
    amount = fields.Decimal(required=False, places=2)
    reason = fields.Str(required=False)

    @validates('amount')
    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise ValidationError('Refund amount must be greater than 0')


class TransactionSchema(Schema):
    """Transaction response schema"""
    id = fields.UUID(dump_only=True)
    idempotency_key = fields.Str(dump_only=True)
    provider = fields.Str(dump_only=True)
    provider_transaction_id = fields.Str(dump_only=True)
    amount = fields.Decimal(places=2, dump_only=True)
    currency = fields.Str(dump_only=True)
    status = fields.Str(dump_only=True)
    customer = fields.Dict(dump_only=True)
    payment_method = fields.Str(dump_only=True)
    metadata = fields.Dict(dump_only=True)
    provider_response = fields.Dict(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    completed_at = fields.DateTime(dump_only=True)