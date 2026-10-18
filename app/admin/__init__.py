# app/admin/__init__.py
from flask import Blueprint
from flask_login import LoginManager

admin = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/admin"
)

from app.admin import routes  # noqa: F401
