# Arquivo: app/__init__.py

from flask import Flask, redirect, url_for
from .config import Config
from .extensions import db, migrate, login_manager

def create_app(config_class=Config):
    """
    Fábrica de aplicação Flask.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # LINHA DE DEBUG TEMPORÁRIA: Adicionada para verificar a chave carregada
    print(f"--- DEBUG: A CHAVE SECRETA CARREGADA É: '{app.config.get('SECRET_KEY')}' ---")

    # Inicializa as extensões
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Registra os Blueprints (módulos da aplicação)
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .gestor import bp as gestor_bp
    app.register_blueprint(gestor_bp, url_prefix='/gestor')

    # Rota principal que agora redireciona para o login
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    return app