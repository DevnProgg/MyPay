from flask import json
from app import create_app, redis_client
from app.extensions import db

app = create_app()

with app.app_context():
    db.create_all()


if __name__ == '__main__':

    app.run(debug=True, host='0.0.0.0', port=5000)