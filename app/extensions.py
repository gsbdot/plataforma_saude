# Arquivo: app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# Apenas declaramos os objetos aqui. A inicialização será feita na fábrica.
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()