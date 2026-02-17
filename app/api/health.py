"""
Health Check and System Monitoring Endpoints
"""

from flask import Blueprint, jsonify
from datetime import datetime
import os
import psutil

from app.extensions import db, redis_client

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Basic health check endpoint

    Returns:
        200 if system is healthy
        503 if system has issues
    """
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'payment-gateway',
        'version': '1.0.0'
    }

    checks = {}
    overall_healthy = True

    # Database check
    try:
        db.session.execute('SELECT 1')
        checks['database'] = {
            'status': 'healthy',
            'message': 'Database connection OK'
        }
    except Exception as e:
        checks['database'] = {
            'status': 'unhealthy',
            'message': f'Database error: {str(e)}'
        }
        overall_healthy = False

    # Redis check
    try:
        redis_client.set('health_check', 'ok', ex=10)
        redis_value = redis_client.get('health_check')
        if redis_value == 'ok':
            checks['redis'] = {
                'status': 'healthy',
                'message': 'Redis connection OK'
            }
        else:
            checks['redis'] = {
                'status': 'unhealthy',
                'message': 'Redis read/write failed'
            }
            overall_healthy = False
    except Exception as e:
        checks['redis'] = {
            'status': 'unhealthy',
            'message': f'Redis error: {str(e)}'
        }
        overall_healthy = False

    health_status['checks'] = checks
    health_status['status'] = 'healthy' if overall_healthy else 'unhealthy'

    status_code = 200 if overall_healthy else 503

    return jsonify(health_status), status_code


@health_bp.route('/health/live', methods=['GET'])
def liveness_probe():
    """
    Kubernetes liveness probe
    Returns 200 if the application is running
    """
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@health_bp.route('/health/ready', methods=['GET'])
def readiness_probe():
    """
    Kubernetes readiness probe
    Returns 200 if the application is ready to serve traffic
    """
    ready = True
    checks = {}

    # Check database
    try:
        db.session.execute('SELECT 1')
        checks['database'] = 'ready'
    except Exception as e:
        checks['database'] = 'not_ready'
        ready = False

    # Check Redis
    try:
        redis_client.client.ping()
        checks['redis'] = 'ready'
    except Exception as e:
        checks['redis'] = 'not_ready'
        ready = False

    status_code = 200 if ready else 503

    return jsonify({
        'status': 'ready' if ready else 'not_ready',
        'checks': checks,
        'timestamp': datetime.utcnow().isoformat()
    }), status_code


@health_bp.route('/metrics', methods=['GET'])
def metrics():
    """
    Basic system metrics

    Returns:
        System and application metrics
    """
    try:
        from app.models import Transaction, WebhookEvent, AuditLog

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Application metrics
        total_transactions = Transaction.query.count()
        pending_transactions = Transaction.query.filter_by(status='pending').count()
        completed_transactions = Transaction.query.filter_by(status='completed').count()
        failed_transactions = Transaction.query.filter_by(status='failed').count()

        total_webhooks = WebhookEvent.query.count()
        processed_webhooks = WebhookEvent.query.filter_by(processed=True).count()
        failed_webhooks = WebhookEvent.query.filter(
            WebhookEvent.processed == False,
            WebhookEvent.retry_count >= 5
        ).count()

        total_audit_logs = AuditLog.query.count()

        # Database connection pool metrics (SQLAlchemy)
        pool = db.engine.pool
        pool_size = pool.size()
        pool_checked_out = pool.checkedout()
        pool_overflow = pool.overflow()

        return jsonify({
            'timestamp': datetime.utcnow().isoformat(),
            'system': {
                'cpu_percent': cpu_percent,
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'percent': memory.percent,
                    'used': memory.used
                },
                'disk': {
                    'total': disk.total,
                    'used': disk.used,
                    'free': disk.free,
                    'percent': disk.percent
                },
                'process': {
                    'pid': os.getpid(),
                    'threads': psutil.Process().num_threads()
                }
            },
            'application': {
                'transactions': {
                    'total': total_transactions,
                    'pending': pending_transactions,
                    'completed': completed_transactions,
                    'failed': failed_transactions
                },
                'webhooks': {
                    'total': total_webhooks,
                    'processed': processed_webhooks,
                    'failed': failed_webhooks
                },
                'audit_logs': {
                    'total': total_audit_logs
                },
                'database_pool': {
                    'size': pool_size,
                    'checked_out': pool_checked_out,
                    'overflow': pool_overflow
                }
            }
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@health_bp.route('/version', methods=['GET'])
def version():
    """
    Get application version information
    """
    return jsonify({
        'service': 'payment-gateway',
        'version': '1.0.0',
        'build_date': '2024-01-01',
        'environment': os.getenv('FLASK_ENV', 'production')
    }), 200