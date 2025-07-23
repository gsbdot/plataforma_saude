# Arquivo: app/decorators.py

from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    """
    Garante que o usuário logado tenha a role 'GESTOR'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'GESTOR':
            flash('Acesso negado. Esta área é restrita aos gestores.', 'danger')
            return redirect(url_for('gestor.dashboard'))
        return f(*args, **kwargs)
    return decorated_function