from flask_socketio import emit, join_room, leave_room
from app.extensions import socketio
from app.models import Transaction


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('connected', {'message': 'Connected to payment gateway'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')


@socketio.on('subscribe_transaction')
def handle_subscribe_transaction(data):
    """Subscribe to transaction updates"""
    transaction_id = data.get('transaction_id')
    if transaction_id:
        room = f'transaction_{transaction_id}'
        join_room(room)
        emit('subscribed', {
            'message': f'Subscribed to transaction {transaction_id}',
            'room': room
        })


@socketio.on('unsubscribe_transaction')
def handle_unsubscribe_transaction(data):
    """Unsubscribe from transaction updates"""
    transaction_id = data.get('transaction_id')
    if transaction_id:
        room = f'transaction_{transaction_id}'
        leave_room(room)
        emit('unsubscribed', {
            'message': f'Unsubscribed from transaction {transaction_id}'
        })


def emit_transaction_update(transaction: Transaction, event_type: str):
    """
    Emit transaction update to subscribed clients

    Args:
        transaction: Transaction object
        event_type: Type of event (e.g., 'payment.completed')
    """
    room = f'transaction_{transaction.id}'

    socketio.emit('transaction_update', {
        'event_type': event_type,
        'transaction': transaction.to_dict()
    }, room=room)

    # Also emit to user-specific room if customer_id exists
    if transaction.customer_id:
        user_room = f'user_{transaction.customer_id}'
        socketio.emit('transaction_update', {
            'event_type': event_type,
            'transaction': transaction.to_dict()
        }, room=user_room)