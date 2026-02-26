from typing import Any

from sqlalchemy.exc import IntegrityError

from app.errors import AppError
from app.extensions import db
from app.errors.exceptions import BadRequest, AccountNotFound
from app.models import Merchant, Account
from app.utils import encrypt_response, hash_string, generate_merchant_api_key


def new_merchant(data : dict) -> dict:
    try:
        merchant = Merchant(
            name=data["name"],
            email=data["email"],
            number=data["number"],
            business_name=data["business_name"],
            business_category=data["business_category"]
        )
        db.session.add(merchant)
        db.session.flush()
        account = Account(
            merchant_id=merchant.id,
            username=data["username"],
            password=hash_string(data["password"]),
            api_key=generate_merchant_api_key()
        )
        db.session.add(account)
        db.session.commit()

        response = {
            "id": merchant.id,
            "name": merchant.name,
            "email": merchant.email,
            "number": merchant.number,
            "business_name": merchant.business_name,
            "business_category": merchant.business_category,
            "api_key": encrypt_response(account.api_key, merchant.id)
        }

        return response

    except IntegrityError:
        db.session.rollback()
        raise BadRequest("Merchant already exists")


def merchant_login(data : dict) -> dict[str, dict | Any] | None:
    try:
        account = Account.query.filter_by(username= data["username"], password= hash_string(data["password"])).first()
        if account:
            merchant = Merchant.query.filter_by(id= account.merchant_id).first()
            if merchant:
                response = {
                    "id": merchant.id,
                    "name": merchant.name,
                    "email": merchant.email,
                    "number": merchant.number,
                    "business_name": merchant.business_name,
                    "business_category": merchant.business_category,
                    "api_key": encrypt_response(account.api_key, merchant.id)
                }
                return response
    except Exception as e:
        raise AppError(str(e))
