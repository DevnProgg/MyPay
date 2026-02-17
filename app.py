import os
from app import create_app, socketio
from app.extensions import db

app = create_app(os.getenv('FLASK_ENV', 'development'))

@app.shell_context_processor
def make_shell_context():
    from app.models import Transaction, AuditLog, WebhookEvent, ProviderConfig
    return {
        'db': db,
        'Transaction': Transaction,
        'AuditLog': AuditLog,
        'WebhookEvent': WebhookEvent,
        'ProviderConfig': ProviderConfig
    }

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)