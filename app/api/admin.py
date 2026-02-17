"""
Admin API Endpoints
Administrative functions for managing the payment gateway
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.providers import list_available_providers, get_provider
from app.services.payment_service import PaymentService
from app.services.audit_service import AuditService
from app.services.webhook_service import WebhookService
from app.models import ProviderConfig
from app.extensions import db

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/providers', methods=['GET'])
def get_providers():
    """
    List all available payment providers

    Returns:
        List of provider names and their status
    """
    try:
        providers = list_available_providers()

        # Get provider configurations from database
        configs = ProviderConfig.query.all()
        config_dict = {config.provider_name: config for config in configs}

        provider_list = []
        for provider in providers:
            config = config_dict.get(provider)
            provider_list.append({
                'name': provider,
                'is_configured': config is not None,
                'is_active': config.is_active if config else False,
                'last_updated': config.updated_at.isoformat() if config else None
            })

        return jsonify({
            'success': True,
            'data': provider_list
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/providers/<provider_name>/config', methods=['POST'])
@jwt_required()
def configure_provider(provider_name):
    """
    Configure a payment provider

    Path Parameters:
        provider_name: Name of the provider to configure

    Body:
        {
            "api_key": "xxx",
            "api_secret": "xxx",
            "webhook_secret": "xxx",
            "is_active": true,
            "config": {
                "additional": "configuration"
            }
        }
    """
    try:
        data = request.get_json()

        # Check if provider exists
        if provider_name not in list_available_providers():
            return jsonify({
                'success': False,
                'error': f'Unknown provider: {provider_name}'
            }), 400

        # Get or create provider config
        config = ProviderConfig.query.filter_by(provider_name=provider_name).first()

        if not config:
            config = ProviderConfig(provider_name=provider_name)
            db.session.add(config)

        # Update configuration
        if 'api_key' in data:
            config.api_key = data['api_key']

        if 'api_secret' in data:
            config.api_secret = data['api_secret']

        if 'webhook_secret' in data:
            config.webhook_secret = data['webhook_secret']

        if 'is_active' in data:
            config.is_active = data['is_active']

        if 'config' in data:
            config.config = data['config']

        db.session.commit()

        return jsonify({
            'success': True,
            'data': config.to_dict(include_secrets=False)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/providers/<provider_name>/config', methods=['GET'])
@jwt_required()
def get_provider_config(provider_name):
    """
    Get provider configuration (without secrets)

    Path Parameters:
        provider_name: Name of the provider
    """
    try:
        config = ProviderConfig.query.filter_by(provider_name=provider_name).first()

        if not config:
            return jsonify({
                'success': False,
                'error': 'Provider not configured'
            }), 404

        return jsonify({
            'success': True,
            'data': config.to_dict(include_secrets=False)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    Get overall payment gateway statistics

    Query Parameters:
        - start_date: Start date (ISO format)
        - end_date: End date (ISO format)
    """
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func
        from app.models import Transaction

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if start_date:
            start_date = datetime.fromisoformat(start_date)
        else:
            start_date = datetime.utcnow() - timedelta(days=30)

        if end_date:
            end_date = datetime.fromisoformat(end_date)
        else:
            end_date = datetime.utcnow()

        # Transaction statistics
        query = Transaction.query.filter(
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date
        )

        total_transactions = query.count()
        completed_transactions = query.filter_by(status='completed').count()
        failed_transactions = query.filter_by(status='failed').count()
        pending_transactions = query.filter_by(status='pending').count()

        # Total volume
        total_volume = db.session.query(
            func.sum(Transaction.amount)
        ).filter(
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date,
            Transaction.status == 'completed'
        ).scalar() or 0

        # By provider
        provider_stats = db.session.query(
            Transaction.provider,
            func.count(Transaction.id).label('count'),
            func.sum(Transaction.amount).label('volume')
        ).filter(
            Transaction.created_at >= start_date,
            Transaction.created_at <= end_date,
            Transaction.status == 'completed'
        ).group_by(Transaction.provider).all()

        # Webhook statistics
        webhook_stats = WebhookService.get_webhook_statistics(
            start_date=start_date,
            end_date=end_date
        )

        # Audit event statistics
        audit_stats = AuditService.get_event_statistics(
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            'success': True,
            'data': {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'transactions': {
                    'total': total_transactions,
                    'completed': completed_transactions,
                    'failed': failed_transactions,
                    'pending': pending_transactions,
                    'success_rate': (
                                completed_transactions / total_transactions * 100) if total_transactions > 0 else 0,
                    'total_volume': float(total_volume)
                },
                'by_provider': [
                    {
                        'provider': provider,
                        'count': count,
                        'volume': float(volume or 0)
                    }
                    for provider, count, volume in provider_stats
                ],
                'webhooks': webhook_stats,
                'audit_events': audit_stats
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/transactions/reconcile', methods=['POST'])
@jwt_required()
def reconcile_transactions():
    """
    Reconcile pending transactions with payment providers

    Verifies the status of all pending transactions
    """
    try:
        from app.models import Transaction

        # Get all pending or processing transactions
        pending_transactions = Transaction.query.filter(
            Transaction.status.in_(['pending', 'processing'])
        ).all()

        reconciled = 0
        errors = []

        for transaction in pending_transactions:
            try:
                PaymentService.verify_payment(transaction.id)
                reconciled += 1
            except Exception as e:
                errors.append({
                    'transaction_id': str(transaction.id),
                    'error': str(e)
                })

        return jsonify({
            'success': True,
            'data': {
                'total_pending': len(pending_transactions),
                'reconciled': reconciled,
                'errors': errors
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/webhooks/retry-failed', methods=['POST'])
@jwt_required()
def retry_failed_webhooks():
    """
    Manually trigger retry of all failed webhooks
    """
    try:
        processed_count = WebhookService.retry_failed_webhooks()

        return jsonify({
            'success': True,
            'data': {
                'processed_count': processed_count,
                'message': f'Processed {processed_count} failed webhooks'
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
def get_audit_logs():
    """
    Get audit logs with filters

    Query Parameters:
        - transaction_id: Filter by transaction ID
        - event_type: Filter by event type
        - user_id: Filter by user ID
        - start_date: Start date (ISO format)
        - end_date: End date (ISO format)
        - page: Page number (default: 1)
        - per_page: Items per page (default: 50)
    """
    try:
        from datetime import datetime
        import uuid as uuid_module

        transaction_id = request.args.get('transaction_id')
        event_type = request.args.get('event_type')
        user_id = request.args.get('user_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)

        # Parse dates
        if start_date:
            start_date = datetime.fromisoformat(start_date)

        if end_date:
            end_date = datetime.fromisoformat(end_date)

        # Parse transaction_id
        if transaction_id:
            transaction_id = uuid_module.UUID(transaction_id)

        pagination = AuditService.get_audit_logs(
            transaction_id=transaction_id,
            event_type=event_type,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page
        )

        return jsonify({
            'success': True,
            'data': {
                'items': [log.to_dict() for log in pagination.items],
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
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500