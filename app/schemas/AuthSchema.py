from marshmallow import Schema, fields


class AuthSchema(Schema):
    """ Response after successful signup """
    id = fields.UUID(dump_only=True)
    name = fields.Str(dump_only=True)
    email = fields.Email(dump_only=True)
    number = fields.Str(dump_only=True)
    business_name = fields.Str(dump_only=True)
    business_category = fields.Str(dump_only=True)
    api_key = fields.Str(dump_only=True)

class SignupSchema(Schema):
    """ Request for signup """
    name = fields.Str(required=True)
    email = fields.Email(required=True)
    number = fields.Str(required=True)
    business_name = fields.Str(required=True)
    business_category = fields.Str(required=True)
    username = fields.Str(required=True)
    password = fields.Str(required=True)

class LoginSchema(Schema):
    """request for login"""
    username = fields.Str(required=True)
    password = fields.Str(required=True)