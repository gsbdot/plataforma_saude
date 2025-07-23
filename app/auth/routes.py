# Arquivo: app/auth/routes.py
from . import bp
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.models import Usuario
from app.extensions import db

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('gestor.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = Usuario.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash('Email ou senha inválidos.', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=True)
        flash('Login realizado com sucesso!', 'success')
        return redirect(url_for('gestor.dashboard'))

    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))