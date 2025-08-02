# Arquivo: app/__init__.py

from flask import Flask, redirect, url_for, session
from .config import Config
from .extensions import db, migrate, login_manager

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'
    @login_manager.user_loader
    def load_user(user_id):
        from .models import Usuario
        prefeitura_id = session.get('prefeitura_id')
        if not prefeitura_id:
            return None
        return Usuario.query.filter_by(id=user_id, prefeitura_id=prefeitura_id).first()

    # --- REGISTRO DO NOVO BLUEPRINT ---
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .gestor import bp as gestor_bp
    app.register_blueprint(gestor_bp, url_prefix='/gestor')

    from .paciente_portal import bp as paciente_portal_bp
    app.register_blueprint(paciente_portal_bp, url_prefix='/portal')
    # --- FIM DO REGISTRO ---

    from .commands import seed_db_command
    app.cli.add_command(seed_db_command)

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    return app