
# app/__init__.py
import os

from flask import Flask
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from flask_login import LoginManager

from app.extensions import db, scheduler
from app.tasks.late_returns import check_late_returns
from app.config import Config

load_dotenv()

# Extensions
migrate = Migrate()
jwt = JWTManager()
mail = Mail()
login_manager = LoginManager()

login_manager.login_view = "admin.admin_login"
login_manager.login_message_category = "warning"


# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    # IMPORTANT: Replace AdminUser with your actual login model.
    from app.models import AdminUser

    # Use int(user_id) only if your model's primary key is an integer.
    return db.session.get(AdminUser, int(user_id))


def create_app():
    app = Flask(__name__)

    # Load configuration first
    app.config.from_object(Config)

    app.config["UPLOAD_FOLDER"] = os.path.join(
        app.root_path, "static", "uploads"
    )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # JWT configuration
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
    app.config["JWT_COOKIE_SECURE"] = not app.debug
    app.config["JWT_COOKIE_CSRF_PROTECT"] = False

    # External configuration
    app.config["ADMIN_EMAIL"] = os.getenv("ADMIN_EMAIL")
    app.config["PAYSTACK_SECRET_KEY"] = os.getenv("PAYSTACK_SECRET_KEY")
    app.config["PAYSTACK_PUBLIC_KEY"] = os.getenv("PAYSTACK_PUBLIC_KEY")
    app.config["DEFAULT_PAYMENT_EMAIL"] = os.getenv(
        "DEFAULT_PAYMENT_EMAIL"
    )

    if not app.config.get("PAYSTACK_SECRET_KEY"):
        raise RuntimeError("PAYSTACK_SECRET_KEY not set")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)

    # Register blueprints
    from app.public.routes import public
    from app.admin.routes import admin

    app.register_blueprint(public)
    # app.register_blueprint(admin)
    app.register_blueprint(admin, url_prefix="/admin")

    # Register scheduled task only once
    if not scheduler.running:
        scheduler.init_app(app)

        if not scheduler.get_job("check_late_returns"):
            scheduler.add_job(
                id="check_late_returns",
                func=check_late_returns,
                trigger="interval",
                minutes=30,
                replace_existing=True,
            )

        scheduler.start()

    return app
