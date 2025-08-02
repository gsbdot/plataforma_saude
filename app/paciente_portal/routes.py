# app/paciente_portal/routes.py
from . import bp
from flask import render_template, request, flash, redirect, url_for, session, current_app
from app.models import (
    Prefeitura, Paciente, MagicLink, Consulta, 
    LogAcessoPaciente, SolicitacaoCorrecao
)
from app.extensions import db
from app.services.messaging_gateway import MessagingGateway # Importa o nosso gateway

import secrets
from datetime import datetime, timedelta

@bp.route('/solicitar-link', methods=['GET', 'POST'])
def solicitar_link():
    if request.method == 'POST':
        subdominio = request.form.get('subdominio')
        cpf = request.form.get('cpf')

        prefeitura = Prefeitura.query.filter_by(subdominio=subdominio).first()
        if not prefeitura:
            flash('Identificador da prefeitura inválido.', 'danger')
            return redirect(url_for('.solicitar_link'))

        paciente = Paciente.query.filter_by(cpf=cpf, prefeitura_id=prefeitura.id).first()
        if not paciente:
            flash('CPF não encontrado para esta prefeitura. Verifique os dados ou entre em contato com a unidade de saúde.', 'danger')
            return redirect(url_for('.solicitar_link'))

        # --- LÓGICA DE ENVIO DO LINK MODIFICADA ---
        
        # 1. Gera o token e o link
        token = secrets.token_urlsafe(32)
        expiracao = datetime.utcnow() + timedelta(minutes=15)
        link_magico = url_for('.validar_link', token=token, _external=True)

        novo_link = MagicLink(
            token=token,
            paciente_id=paciente.id,
            prefeitura_id=prefeitura.id,
            expira_em=expiracao
        )
        db.session.add(novo_link)
        db.session.commit()
        
        # 2. Prepara a mensagem e usa o Gateway para "enviar"
        try:
            mensagem = f"Olá, {paciente.nome_completo.split(' ')[0]}! Acesse seu portal de saúde através do link seguro: {link_magico}"
            
            # Instancia o gateway e envia a mensagem
            messaging_service = MessagingGateway(current_app.config)
            messaging_service.enviar_mensagem(paciente.telefone_whatsapp, mensagem)
            
            # Atualiza o feedback para o usuário
            flash('Um link de acesso seguro foi enviado para o seu número de telefone cadastrado.', 'success')
        
        except Exception as e:
            # Em caso de falha no envio, informa o erro
            flash(f'Não foi possível enviar o link de acesso. Por favor, tente novamente mais tarde. Erro: {e}', 'danger')

        # --- FIM DA MODIFICAÇÃO ---
        
        return redirect(url_for('.solicitar_link'))

    return render_template('solicitar_link.html')

@bp.route('/validar-link/<token>')
def validar_link(token):
    link = MagicLink.query.filter_by(token=token, usado=False).first()

    if not link or datetime.utcnow() > link.expira_em:
        flash('Link de acesso inválido ou expirado. Por favor, solicite um novo.', 'danger')
        return redirect(url_for('.solicitar_link'))
    
    link.usado = True
    db.session.commit()

    session['paciente_id'] = link.paciente_id
    session['prefeitura_id_paciente'] = link.prefeitura_id

    flash('Acesso autorizado com sucesso!', 'success')
    return redirect(url_for('.dashboard'))

@bp.route('/dashboard')
def dashboard():
    paciente_id = session.get('paciente_id')
    if not paciente_id:
        return redirect(url_for('.solicitar_link'))
    
    paciente = Paciente.query.get_or_404(paciente_id)
    consultas = Consulta.query.filter_by(paciente_id=paciente.id).order_by(Consulta.data_inicio.desc()).all()
    logs_acesso = LogAcessoPaciente.query.filter_by(paciente_id=paciente.id).order_by(LogAcessoPaciente.timestamp.desc()).all()
    
    return render_template('dashboard.html', paciente=paciente, consultas=consultas, logs_acesso=logs_acesso)

@bp.route('/logout')
def logout():
    session.pop('paciente_id', None)
    session.pop('prefeitura_id_paciente', None)
    flash('Você saiu do portal do paciente.', 'info')
    return redirect(url_for('.solicitar_link'))

@bp.route('/solicitar-correcao', methods=['POST'])
def solicitar_correcao():
    paciente_id = session.get('paciente_id')
    prefeitura_id = session.get('prefeitura_id_paciente')
    if not paciente_id:
        flash('Sua sessão expirou. Por favor, acesse novamente.', 'warning')
        return redirect(url_for('.solicitar_link'))
    
    campo = request.form.get('campo')
    justificativa = request.form.get('justificativa')

    if not campo or not justificativa:
        flash('É necessário selecionar o campo e descrever a correção.', 'danger')
        return redirect(url_for('.dashboard'))

    nova_solicitacao = SolicitacaoCorrecao(
        paciente_id=paciente_id,
        prefeitura_id=prefeitura_id,
        campo=campo,
        justificativa=justificativa
    )
    db.session.add(nova_solicitacao)
    db.session.commit()

    flash('Sua solicitação de correção foi enviada com sucesso e será analisada pela equipe de gestão.', 'success')
    return redirect(url_for('.dashboard'))