from flask import Blueprint

pantry_bp = Blueprint('pantry', __name__)

from . import routes
