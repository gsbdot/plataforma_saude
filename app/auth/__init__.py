# app/auth/__init__.py
from flask import Blueprint

bp = Blueprint('auth', __name__, template_folder='templates')

# Importa as rotas no final para evitar importações circulares
from . import routes