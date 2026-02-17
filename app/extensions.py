from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from redis import Redis

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
socketio = SocketIO()


class RedisClient:
    def __init__(self):
        self.client = None

    def init_app(self, app):
        import redis
        redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        self.client = redis.from_url(redis_url, decode_responses=True)

    def get(self, key):
        return self.client.get(key)

    def set(self, key, value, ex=None):
        return self.client.set(key, value, ex=ex)

    def delete(self, key):
        return self.client.delete(key)

    def exists(self, key):
        return self.client.exists(key)


redis_client = RedisClient()