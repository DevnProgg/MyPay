from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy

from app.extentions.celery_extention import create_celery

jwt = JWTManager()
db = SQLAlchemy()
celery_app = create_celery()


class RedisClient:
    def __init__(self):
        self.client = None

    def init_app(self, app):
        import redis
        from app.config import Config
        self.client = redis.client.StrictRedis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=Config.REDIS_DB)

    def get(self, key):
        return self.client.get(key)

    def set(self, key, value, ex=None):
        return self.client.set(key, value, ex=ex)

    def delete(self, key):
        return self.client.delete(key)

    def exists(self, key):
        return self.client.exists(key)


redis_client = RedisClient()



