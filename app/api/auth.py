
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError
from app.errors.exceptions import BadRequest, AccountNotFound
from app.schemas.AuthSchema import SignupSchema, AuthSchema, LoginSchema
from app.services.auth_service import new_merchant, merchant_login

auth_bp = Blueprint("auth", __name__)
signup_schema = SignupSchema()
auth_schema = AuthSchema()
login_schema = LoginSchema()

@auth_bp.route("/signup", methods=["POST"])
def signup():
    """
    Signup route to create a new merchant    :return:  merchant information
    """
    try:
        data = signup_schema.load(request.json)

        response = new_merchant(data)
        return jsonify({
            "success" : True,
            "data" : auth_schema.dump(response)
            }), 201

    except ValidationError as err:
        raise BadRequest(err.messages)

@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Login route to check login credentials
    :return: merchant information
    """
    try:
        data = login_schema.load(request.json)
        response = merchant_login(data)

        if response is None:
            raise AccountNotFound("Merchant not found")

        return jsonify({
            "success" : True,
            "data" : auth_schema.dump(response)
        })

    except ValidationError as err:
        raise BadRequest(err.messages)