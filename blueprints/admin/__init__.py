from flask import Blueprint

admin_bp = Blueprint('admin_panel', __name__)

from . import routes
