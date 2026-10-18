from flask import Blueprint

public_bp = Blueprint(
    "public",
    __name__,
    template_folder="templates",   # make sure this is correct
    static_folder="static"         # if you have public static files
)

from app.public import routes
