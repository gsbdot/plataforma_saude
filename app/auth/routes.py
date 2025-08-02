# Arquivo: app/auth/routes.py

# A linha de print foi removida daqui
from . import bp
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user
from app.models import Usuario, Prefeitura
from app.extensions import db

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('gestor.dashboard'))
    
    if request.method == 'POST':
        subdominio = request.form.get('subdominio')
        email = request.form.get('email')
        password = request.form.get('password')

        prefeitura = Prefeitura.query.filter_by(subdominio=subdominio).first()

        if not prefeitura:
            flash('Identificador da prefeitura inválido ou não encontrado.', 'danger')
            return redirect(url_for('auth.login'))

        user = Usuario.query.filter_by(email=email, prefeitura_id=prefeitura.id).first()

        if user is None or not user.check_password(password) or not user.is_active:
            flash('Email ou senha inválidos para esta prefeitura.', 'danger')
            return redirect(url_for('auth.login'))
        
        session['prefeitura_id'] = prefeitura.id
        
        login_user(user, remember=True)
        flash('Login realizado com sucesso!', 'success')
        return redirect(url_for('gestor.dashboard'))

    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    logout_user()
    session.pop('prefeitura_id', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))