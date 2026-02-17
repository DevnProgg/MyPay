"""
Unit Tests for Idempotency Service
"""

import pytest
import json
from unittest.mock import Mock, patch
from app.services.idempotency_service import IdempotencyService


class TestIdempotencyService:
    """Test cases for IdempotencyService"""

    def test_get_key(self):
        """Test idempotency key generation"""
        key = IdempotencyService.get_key('test-key-123')
        assert key == 'idempotency:test-key-123'

    def test_get_cached_response_not_found(self, redis_client):
        """Test getting cached response when not found"""
        result = IdempotencyService.get_cached_response('nonexistent-key')
        assert result is None

    def test_cache_and_get_response(self, redis_client):
        """Test caching and retrieving response"""
        test_data = {'status': 'success', 'data': 'test'}

        # Cache the response
        IdempotencyService.cache_response('test-key', test_data, ttl=60)

        # Retrieve it
        cached = IdempotencyService.get_cached_response('test-key')

        assert cached is not None
        assert cached['status'] == 'success'
        assert cached['data'] == 'test'

    def test_delete_cached_response(self, redis_client):
        """Test deleting cached response"""
        test_data = {'status': 'success'}

        # Cache the response
        IdempotencyService.cache_response('test-key', test_data)

        # Verify it exists
        assert IdempotencyService.get_cached_response('test-key') is not None

        # Delete it
        IdempotencyService.delete_cached_response('test-key')

        # Verify it's gone
        assert IdempotencyService.get_cached_response('test-key') is None

    def test_cache_response_with_ttl(self, redis_client):
        """Test caching with TTL"""
        test_data = {'status': 'success'}

        # Cache with 1 second TTL
        IdempotencyService.cache_response('test-key', test_data, ttl=1)

        # Should be available immediately
        assert IdempotencyService.get_cached_response('test-key') is not None

        # Wait for expiration
        import time
        time.sleep(2)

        # Should be expired
        assert IdempotencyService.get_cached_response('test-key') is None

    def test_cache_complex_data(self, redis_client):
        """Test caching complex nested data"""
        complex_data = {
            'transaction': {
                'id': '123',
                'amount': 1000.00,
                'items': [
                    {'name': 'Item 1', 'price': 500.00},
                    {'name': 'Item 2', 'price': 500.00}
                ]
            },
            'status': 'completed'
        }

        IdempotencyService.cache_response('complex-key', complex_data)
        cached = IdempotencyService.get_cached_response('complex-key')

        assert cached is not None
        assert cached['transaction']['id'] == '123'
        assert len(cached['transaction']['items']) == 2


class TestIdempotentDecorator:
    """Test cases for @idempotent decorator"""

    def test_idempotent_decorator_first_call(self, client, redis_client):
        """Test first call with idempotency key"""
        from flask import Flask, jsonify
        from app.services.idempotency_service import idempotent

        app = Flask(__name__)

        @app.route('/test', methods=['POST'])
        @idempotent(ttl=60)
        def test_endpoint():
            return jsonify({'result': 'success', 'call': 'original'}), 201

        with app.test_client() as client:
            response = client.post(
                '/test',
                headers={'Idempotency-Key': 'test-key-123'}
            )

            assert response.status_code == 201
            data = json.loads(response.data)
            assert data['result'] == 'success'
            assert data['call'] == 'original'

    def test_idempotent_decorator_duplicate_call(self, client, redis_client):
        """Test duplicate call returns cached response"""
        from flask import Flask, jsonify
        from app.services.idempotency_service import idempotent

        app = Flask(__name__)

        call_count = {'count': 0}

        @app.route('/test', methods=['POST'])
        @idempotent(ttl=60)
        def test_endpoint():
            call_count['count'] += 1
            return jsonify({
                'result': 'success',
                'call_count': call_count['count']
            }), 201

        with app.test_client() as client:
            # First call
            response1 = client.post(
                '/test',
                headers={'Idempotency-Key': 'duplicate-key'}
            )
            data1 = json.loads(response1.data)

            # Second call with same key
            response2 = client.post(
                '/test',
                headers={'Idempotency-Key': 'duplicate-key'}
            )
            data2 = json.loads(response2.data)

            # Both should return same data
            assert data1['call_count'] == 1
            assert data2['call_count'] == 1  # Not incremented

            # Function should only be called once
            assert call_count['count'] == 1

    def test_idempotent_decorator_missing_key(self, client):
        """Test decorator requires idempotency key"""
        from flask import Flask, jsonify
        from app.services.idempotency_service import idempotent

        app = Flask(__name__)

        @app.route('/test', methods=['POST'])
        @idempotent(ttl=60)
        def test_endpoint():
            return jsonify({'result': 'success'}), 201

        with app.test_client() as client:
            response = client.post('/test')  # No idempotency key

            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'Idempotency-Key' in data['error']

    def test_idempotent_decorator_different_keys(self, client, redis_client):
        """Test different keys call function separately"""
        from flask import Flask, jsonify
        from app.services.idempotency_service import idempotent

        app = Flask(__name__)

        call_count = {'count': 0}

        @app.route('/test', methods=['POST'])
        @idempotent(ttl=60)
        def test_endpoint():
            call_count['count'] += 1
            return jsonify({
                'result': 'success',
                'call_count': call_count['count']
            }), 201

        with app.test_client() as client:
            # Call with first key
            response1 = client.post(
                '/test',
                headers={'Idempotency-Key': 'key-1'}
            )
            data1 = json.loads(response1.data)

            # Call with second key
            response2 = client.post(
                '/test',
                headers={'Idempotency-Key': 'key-2'}
            )
            data2 = json.loads(response2.data)

            # Both should have different call counts
            assert data1['call_count'] == 1
            assert data2['call_count'] == 2

            # Function should be called twice
            assert call_count['count'] == 2

    def test_idempotent_decorator_custom_ttl(self, redis_client):
        """Test decorator with custom TTL"""
        from flask import Flask, jsonify
        from app.services.idempotency_service import idempotent

        app = Flask(__name__)

        @app.route('/test', methods=['POST'])
        @idempotent(ttl=1)  # 1 second TTL
        def test_endpoint():
            return jsonify({'result': 'success'}), 201

        with app.test_client() as client:
            # First call
            response1 = client.post(
                '/test',
                headers={'Idempotency-Key': 'ttl-test-key'}
            )
            assert response1.status_code == 201

            # Immediate second call - should return cached
            response2 = client.post(
                '/test',
                headers={'Idempotency-Key': 'ttl-test-key'}
            )
            assert response2.status_code == 200

            # Wait for expiration
            import time
            time.sleep(2)

            # Third call - should execute again
            response3 = client.post(
                '/test',
                headers={'Idempotency-Key': 'ttl-test-key'}
            )
            assert response3.status_code == 201