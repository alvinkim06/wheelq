from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from flask_caching import Cache

scheduler = APScheduler()

db = SQLAlchemy()

cache = Cache()
