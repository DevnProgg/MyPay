from flask import Blueprint, request, jsonify
from marshmallow import ValidationError

from app.errors import AppError, PaymentNotFound
from app.schemas.payment_schema import (
    InitializePaymentSchema,
    TransactionSchema
)
from app.services.payment_service import PaymentService
from app.services.idempotency_service import idempotent
from app.utils.authorization import api_key_required

payments_bp = Blueprint('payments', __name__)

initialize_schema = InitializePaymentSchema()
transaction_schema = TransactionSchema()


@payments_bp.route('/initialize', methods=['POST'])
@idempotent(ttl=86400)
@api_key_required()
def initialize_payment():
    """
    Initialize a payment

    Headers:
        - Idempotency-Key: for request idempotency
        - X-API_key : for request api key authentication

    Body:
        {
            "provider": "mpesa",
            "amount": 1000.00,
            "currency": "LSL",
            "customer": {
                "phone": "+26657502734",
                "email": "customer@example.com",
                "name": "John Doe"
            }
        }
    """
    try:
        # Validate request data
        data = initialize_schema.load(request.json)

        # Get idempotency key
        idempotency_key = request.headers.get('Idempotency-Key')

        #Get api key
        api_key = request.headers.get('X-API_Key')

        # Initialize payment
        transaction = PaymentService.initialize_payment(
            provider=data['provider'],
            amount=data['amount'],
            currency=data['currency'],
            customer_data=data['customer'],
            metadata=data.get('metadata'),
            idempotency_key=idempotency_key,
            api_key=api_key
        )

        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 201

    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': 'Validation error',
            'details': e.messages
        }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@payments_bp.route('/<uuid:transaction_id>', methods=['GET'])
@api_key_required()
def get_payment(transaction_id):
    """
    Get payment details

    Path Parameters:
        - transaction_id: Transaction UUID
    """
    try:
        transaction = PaymentService.get_transaction(transaction_id)

        if not transaction:
            raise PaymentNotFound(str(transaction_id))

        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 200

    except Exception as e:
        raise AppError(str(e))


@payments_bp.route('/<uuid:transaction_id>/verify', methods=['POST'])
@api_key_required()
def verify_payment(transaction_id):
    """
    Verify payment status with provider

    Path Parameters:
        - transaction_id: Transaction UUID
    """
    try:

        transaction = PaymentService.verify_payment(transaction_id, request.headers.get("Authorization"))

        return jsonify({
            'success': True,
            'data': transaction_schema.dump(transaction)
        }), 200

    except ValueError as e:
        raise PaymentNotFound(str(e))

    except Exception as e:
        raise AppError(str(e))



@payments_bp.route('/payments', methods=['GET'])
@api_key_required()
def list_payments():
    """
    List payments with filters

    Query Parameters:
        - provider: Filter by provider (optional)
        - status: Filter by status (optional)
        - customer_id: Filter by customer (optional)
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20, max: 100)
    """
    try:
        provider = request.args.get('provider')
        status = request.args.get('status')
        customer_id = request.args.get('customer_id')
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 20)), 100)

        pagination = PaymentService.list_transactions(
            provider=provider,
            status=status,
            customer_id=customer_id,
            page=page,
            per_page=per_page
        )

        return jsonify({
            'success': True,
            'data': {
                'items': transaction_schema.dump(pagination.items, many=True),
                'pagination': {
                    'page': pagination.page,
                    'per_page': pagination.per_page,
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            }
        }), 200

    except Exception as e:
       raise PaymentNotFound(str(e))