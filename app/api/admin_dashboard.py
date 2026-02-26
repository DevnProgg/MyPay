"""
Admin Dashboard Blueprint
Serves the Flask-rendered admin UI with session-based authentication.
All routes are guarded — unauthenticated users are redirected to /admin/login.
"""

import requests
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, current_app
)

admin_dashboard_bp = Blueprint(
    'admin_dashboard',
    __name__,
    template_folder='../templates'
)

# Auth guard decorator

def login_required(f):
    """Redirect to login page if no active admin session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_token' not in session:
            flash('Please log in to access the admin dashboard.', 'warning')
            return redirect(url_for('admin_dashboard.login'))
        return f(*args, **kwargs)
    return decorated


def _api(path, method='GET', json=None, params=None):
    """
    Internal helper: call the payment-gateway API using the token stored in the
    current admin session.  Returns the parsed JSON response dict (or an empty
    dict on error).
    """
    base = current_app.config.get('API_BASE_URL', 'http://127.0.0.1:5000/api/v1')
    headers = {
        'Authorization': f"Bearer {session.get('admin_token', '')}",
        'Content-Type': 'application/json',
    }
    try:
        resp = requests.request(
            method,
            f"{base}{path}",
            headers=headers,
            json=json,
            params=params,
            timeout=10,
        )
        return resp.json()
    except Exception as exc:
        current_app.logger.error(f"API call failed [{method} {path}]: {exc}")
        return {'success': False, 'error': str(exc)}


# Auth routes

@admin_dashboard_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Display and handle the admin login form."""
    if 'admin_token' in session:
        return redirect(url_for('admin_dashboard.dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Exchange credentials for a JWT via the existing auth endpoint.
        base = current_app.config.get('API_BASE_URL', 'http://localhost:5000/api/v1/')
        try:
            resp = requests.post(
                f"{base}/auth/admin/login",
                json={'username': username, 'password': password},
                timeout=10,
            )
            data = resp.json()
            if resp.ok and data.get('success'):
                session.permanent = True
                session['admin_token'] = data['data']['access_token']
                session['admin_user'] = username
                flash('Welcome back!', 'success')
                return redirect(url_for('admin_dashboard.dashboard'))
            else:
                error = data.get('error', 'Invalid credentials.')
        except Exception as exc:
            error = f"Could not reach the API: {exc}"

    return render_template('login.html', error=error)


@admin_dashboard_bp.route('/logout')
def logout():
    """Clear the admin session and redirect to login."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_dashboard.login'))


# Dashboard

@admin_dashboard_bp.route('/')
@login_required
def dashboard():
    """Main overview dashboard — statistics + recent transactions."""
    stats = _api('/admin/statistics')
    health = _api('/health')
    providers = _api('/admin/providers')

    context = {
        'page': 'dashboard',
        'stats': stats.get('data', {}),
        'health': health,
        'providers': providers.get('data', []),
        'admin_user': session.get('admin_user'),
    }
    return render_template('dashboard.html', **context)

# Transactions


@admin_dashboard_bp.route('/transactions')
@login_required
def transactions():
    """Paginated transaction list with filters."""
    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    provider = request.args.get('provider', '')
    status   = request.args.get('status', '')

    params = {'page': page, 'per_page': per_page}
    if provider:
        params['provider'] = provider
    if status:
        params['status'] = status

    data = _api('/payments', params=params)
    context = {
        'page': 'transactions',
        'result': data.get('data', {}),
        'filters': {'provider': provider, 'status': status},
        'admin_user': session.get('admin_user'),
    }
    return render_template('transactions.html', **context)


@admin_dashboard_bp.route('/transactions/<transaction_id>')
@login_required
def transaction_detail(transaction_id):
    """Single transaction detail view."""
    data = _api(f'/payments/{transaction_id}')
    context = {
        'page': 'transactions',
        'transaction': data.get('data', {}),
        'admin_user': session.get('admin_user'),
    }
    return render_template('transaction_detail.html', **context)


@admin_dashboard_bp.route('/transactions/reconcile', methods=['POST'])
@login_required
def reconcile():
    """Trigger reconciliation of pending transactions."""
    result = _api('/admin/transactions/reconcile', method='POST')
    flash(
        f"Reconciled {result.get('data', {}).get('reconciled', 0)} transactions.",
        'success' if result.get('success') else 'danger'
    )
    return redirect(url_for('admin_dashboard.transactions'))

# Webhooks

@admin_dashboard_bp.route('/webhooks')
@login_required
def webhooks():
    """Webhook event list with filters."""
    page      = int(request.args.get('page', 1))
    per_page  = int(request.args.get('per_page', 50))
    provider  = request.args.get('provider', '')
    processed = request.args.get('processed', '')
    verified  = request.args.get('verified', '')

    params = {'page': page, 'per_page': per_page}
    if provider:   params['provider'] = provider
    if processed:  params['processed'] = processed
    if verified:   params['verified'] = verified

    events = _api('/webhooks/events', params=params)
    dlq    = _api('/webhooks/dead-letter-queue')
    stats  = _api('/webhooks/statistics')

    context = {
        'page': 'webhooks',
        'result': events.get('data', {}),
        'dlq': dlq.get('data', {}),
        'stats': stats.get('data', {}),
        'filters': {'provider': provider, 'processed': processed, 'verified': verified},
        'admin_user': session.get('admin_user'),
    }
    return render_template('webhooks.html', **context)


@admin_dashboard_bp.route('/webhooks/<event_id>/retry', methods=['POST'])
@login_required
def retry_webhook(event_id):
    """Retry a single failed webhook."""
    result = _api(f'/webhooks/events/{event_id}/retry', method='POST')
    flash(
        'Webhook retried successfully.' if result.get('success') else 'Retry failed.',
        'success' if result.get('success') else 'danger'
    )
    return redirect(url_for('admin_dashboard.webhooks'))


@admin_dashboard_bp.route('/webhooks/retry-all', methods=['POST'])
@login_required
def retry_all_webhooks():
    """Retry all failed webhooks."""
    result = _api('/admin/webhooks/retry-failed', method='POST')
    flash(
        result.get('data', {}).get('message', 'Done.'),
        'success' if result.get('success') else 'danger'
    )
    return redirect(url_for('admin_dashboard.webhooks'))


# Audit Logs

@admin_dashboard_bp.route('/audit-logs')
@login_required
def audit_logs():
    """Audit log viewer with filters."""
    page           = int(request.args.get('page', 1))
    per_page       = int(request.args.get('per_page', 50))
    transaction_id = request.args.get('transaction_id', '')
    event_type     = request.args.get('event_type', '')
    user_id        = request.args.get('user_id', '')
    start_date     = request.args.get('start_date', '')
    end_date       = request.args.get('end_date', '')

    params = {'page': page, 'per_page': per_page}
    if transaction_id: params['transaction_id'] = transaction_id
    if event_type:     params['event_type'] = event_type
    if user_id:        params['user_id'] = user_id
    if start_date:     params['start_date'] = start_date
    if end_date:       params['end_date'] = end_date

    data = _api('/admin/audit-logs', params=params)
    context = {
        'page': 'audit',
        'result': data.get('data', {}),
        'filters': {
            'transaction_id': transaction_id,
            'event_type': event_type,
            'user_id': user_id,
            'start_date': start_date,
            'end_date': end_date,
        },
        'admin_user': session.get('admin_user'),
    }
    return render_template('audit_logs.html', **context)

# System Health

@admin_dashboard_bp.route('/health')
@login_required
def system_health():
    """System health and metrics page."""
    health  = _api('/health')
    metrics = _api('/health/metrics')
    context = {
        'page': 'health',
        'health': health,
        'metrics': metrics,
        'admin_user': session.get('admin_user'),
    }
    return render_template('health.html', **context)


# Providers

@admin_dashboard_bp.route('/providers')
@login_required
def providers():
    """Payment provider configuration overview."""
    data = _api('/admin/providers')
    context = {
        'page': 'providers',
        'providers': data.get('data', []),
        'admin_user': session.get('admin_user'),
    }
    return render_template('providers.html', **context)