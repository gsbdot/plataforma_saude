# app/gestor/__init__.py
from flask import Blueprint

bp = Blueprint('gestor', __name__, template_folder='templates')

from . import routes