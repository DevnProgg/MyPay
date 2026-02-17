"""
Audit Service
Handles comprehensive audit logging for all payment transactions
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from flask import request

from app.extensions import db
from app.models import AuditLog


class AuditService:
    """Service for creating and managing audit logs"""

    @staticmethod
    def log_event(
            transaction_id: uuid.UUID,
            event_type: str,
            event_data: Dict[str, Any],
            user_id: Optional[str] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Create an audit log entry

        Args:
            transaction_id: UUID of the transaction
            event_type: Type of event (e.g., 'payment.initiated', 'payment.completed')
            event_data: Additional event data
            user_id: User ID if available
            ip_address: IP address of the request
            user_agent: User agent string

        Returns:
            Created AuditLog object
        """
        # Try to extract request context if not provided
        if request:
            if not ip_address:
                ip_address = AuditService._get_client_ip()
            if not user_agent:
                user_agent = request.headers.get('User-Agent')

        audit_log = AuditLog(
            transaction_id=transaction_id,
            event_type=event_type,
            event_data=event_data,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

        db.session.add(audit_log)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Log to application logger
            import logging
            logging.error(f'Failed to create audit log: {str(e)}')
            raise

        return audit_log

    @staticmethod
    def get_transaction_audit_trail(transaction_id: uuid.UUID) -> list:
        """
        Get complete audit trail for a transaction

        Args:
            transaction_id: UUID of the transaction

        Returns:
            List of audit log entries ordered by timestamp
        """
        return AuditLog.query.filter_by(
            transaction_id=transaction_id
        ).order_by(AuditLog.timestamp.asc()).all()

    @staticmethod
    def get_audit_logs(
            transaction_id: Optional[uuid.UUID] = None,
            event_type: Optional[str] = None,
            user_id: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            page: int = 1,
            per_page: int = 50
    ):
        """
        Get audit logs with filters

        Args:
            transaction_id: Filter by transaction ID
            event_type: Filter by event type
            user_id: Filter by user ID
            start_date: Filter by start date
            end_date: Filter by end date
            page: Page number
            per_page: Items per page

        Returns:
            Paginated audit logs
        """
        query = AuditLog.query

        if transaction_id:
            query = query.filter_by(transaction_id=transaction_id)

        if event_type:
            query = query.filter_by(event_type=event_type)

        if user_id:
            query = query.filter_by(user_id=user_id)

        if start_date:
            query = query.filter(AuditLog.timestamp >= start_date)

        if end_date:
            query = query.filter(AuditLog.timestamp <= end_date)

        return query.order_by(AuditLog.timestamp.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

    @staticmethod
    def _get_client_ip() -> Optional[str]:
        """
        Get client IP address from request
        Handles proxy headers (X-Forwarded-For, X-Real-IP)

        Returns:
            Client IP address
        """
        if not request:
            return None

        # Check for proxy headers
        if request.headers.get('X-Forwarded-For'):
            # X-Forwarded-For can contain multiple IPs, get the first one
            ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            ip = request.headers.get('X-Real-IP')
        else:
            ip = request.remote_addr

        return ip

    @staticmethod
    def create_bulk_audit_logs(entries: list) -> int:
        """
        Create multiple audit log entries in bulk

        Args:
            entries: List of dicts containing audit log data
                Each dict should have: transaction_id, event_type, event_data

        Returns:
            Number of logs created
        """
        audit_logs = []

        for entry in entries:
            audit_log = AuditLog(
                transaction_id=entry['transaction_id'],
                event_type=entry['event_type'],
                event_data=entry['event_data'],
                user_id=entry.get('user_id'),
                ip_address=entry.get('ip_address'),
                user_agent=entry.get('user_agent')
            )
            audit_logs.append(audit_log)

        db.session.bulk_save_objects(audit_logs)

        try:
            db.session.commit()
            return len(audit_logs)
        except Exception as e:
            db.session.rollback()
            import logging
            logging.error(f'Failed to create bulk audit logs: {str(e)}')
            raise

    @staticmethod
    def get_event_statistics(
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """
        Get statistics on event types

        Args:
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            Dict with event types as keys and counts as values
        """
        from sqlalchemy import func

        query = db.session.query(
            AuditLog.event_type,
            func.count(AuditLog.id).label('count')
        )

        if start_date:
            query = query.filter(AuditLog.timestamp >= start_date)

        if end_date:
            query = query.filter(AuditLog.timestamp <= end_date)

        results = query.group_by(AuditLog.event_type).all()

        return {event_type: count for event_type, count in results}

    @staticmethod
    def search_audit_logs(
            search_term: str,
            page: int = 1,
            per_page: int = 50
    ):
        """
        Search audit logs by event data content

        Args:
            search_term: Term to search for in event_data
            page: Page number
            per_page: Items per page

        Returns:
            Paginated search results
        """
        # PostgreSQL JSONB search
        from sqlalchemy import cast, String

        query = AuditLog.query.filter(
            cast(AuditLog.event_data, String).contains(search_term)
        )

        return query.order_by(AuditLog.timestamp.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )