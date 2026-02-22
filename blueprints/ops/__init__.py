from flask import Blueprint

ops_bp = Blueprint('ops', __name__)

from . import routes
