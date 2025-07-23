# Arquivo: app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    """
    O user_loader é usado pelo Flask-Login para recarregar o objeto do usuário 
    a partir do ID armazenado na sessão.
    """
    from .models import Usuario
    # --- MODIFIQUE ESTA LINHA ---
    return db.session.get(Usuario, user_id)
    # --------------------------