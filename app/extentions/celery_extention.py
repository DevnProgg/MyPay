from celery import Celery


def create_celery(app=None):
    celery = Celery(__name__)

    if app:
        init_celery(celery, app)

    return celery


def init_celery(celery, app):
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_track_started=True,
        task_time_limit=30 * 60,
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask