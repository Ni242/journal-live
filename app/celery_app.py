from celery import Celery
import os
from dotenv import load_dotenv
load_dotenv()
broker = os.getenv('CELERY_BROKER_URL', os.getenv('REDIS_URL','redis://localhost:6379/0'))
celery_app = Celery('trading_journal', broker=broker)
celery_app.conf.task_routes = {'app.tasks.*': {'queue': 'tasks'}}
