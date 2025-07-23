# Arquivo: app/gestor/routes.py

from . import bp
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models import (
    Usuario, Paciente, Consulta, Documento, Configuracao, 
    Tarefa, MensagemChatbot, BibliotecaConteudo, LogUso
)
from app.extensions import db
from app.decorators import admin_required
import datetime
import uuid 
from sqlalchemy import func

@bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'GESTOR':
        usuarios = Usuario.query.order_by(Usuario.nome_completo).all()
        return render_template('gestor/dashboard.html', usuarios=usuarios)
    else:
        # Lógica do Profissional
        fila_acolhimento = Paciente.query.filter_by(status='AGUARDANDO_ACOLHIMENTO').all()
        fila_medica = Paciente.query.filter_by(status='AGUARDANDO_MEDICO').all()
        em_atendimento = Consulta.query.filter_by(profissional_id=current_user.id, status='INICIADA').first()
        hoje = datetime.date.today()
        inicio_dia = datetime.datetime.combine(hoje, datetime.time.min)
        fim_dia = datetime.datetime.combine(hoje, datetime.time.max)
        atendimentos_dia = Consulta.query.filter(
            Consulta.profissional_id == current_user.id,
            Consulta.status.in_(['FINALIZADA', 'TRANSFERIDO']),
            Consulta.data_fim.between(inicio_dia, fim_dia)
        ).order_by(Consulta.data_fim.desc()).limit(5).all()
        agenda_do_dia = Consulta.query.filter(
            Consulta.profissional_id == current_user.id,
            Consulta.tipo == 'ELETIVA',
            Consulta.status == 'AGENDADA',
            Consulta.data_inicio.between(inicio_dia, fim_dia)
        ).order_by(Consulta.data_inicio.asc()).all()
        tarefas_pendentes = Tarefa.query.filter_by(
            atribuido_para_id=current_user.id,
            status='PENDENTE'
        ).order_by(Tarefa.data_criacao.asc()).all()
        outros_profissionais = Usuario.query.filter(
            Usuario.id != current_user.id, 
            Usuario.role == 'PROFISSIONAL_SAUDE'
        ).order_by(Usuario.nome_completo).all()
        return render_template(
            'profissional/dashboard.html',
            fila_acolhimento=fila_acolhimento,
            fila_medica=fila_medica,
            em_atendimento=em_atendimento,
            atendimentos_dia=atendimentos_dia,
            agenda_do_dia=agenda_do_dia,
            tarefas_pendentes=tarefas_pendentes,
            outros_profissionais=outros_profissionais
        )

# --- ROTAS DE ATENDIMENTO ---

@bp.route('/atendimento/iniciar/<int:paciente_id>/<string:tipo_atendimento>', methods=['POST'])
@login_required
def iniciar_atendimento(paciente_id, tipo_atendimento):
    atendimento_existente = Consulta.query.filter_by(profissional_id=current_user.id, status='INICIADA').first()
    if atendimento_existente:
        flash('Você já possui um atendimento em andamento. Finalize-o antes de chamar um novo paciente.', 'warning')
        return redirect(url_for('gestor.dashboard'))
    paciente = Paciente.query.get_or_404(paciente_id)
    paciente.status = 'EM_ATENDIMENTO'
    nova_consulta = Consulta(
        uuid=str(uuid.uuid4()),
        paciente_id=paciente.id,
        profissional_id=current_user.id,
        status='INICIADA',
        tipo=tipo_atendimento,
        data_inicio=datetime.datetime.utcnow()
    )
    db.session.add(nova_consulta)
    
    # Gatilho de Log de Uso
    log = LogUso(
        event_type='CONSULTA_INICIADA',
        unit='consulta',
        related_usuario_id=current_user.id
    )
    db.session.add(log)
    
    db.session.commit()

    log.related_consulta_id = nova_consulta.id
    db.session.commit()
    
    flash(f'Atendimento com {paciente.nome_completo} iniciado.', 'success')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/atendimento/finalizar/<int:consulta_id>', methods=['POST'])
@login_required
def finalizar_atendimento(consulta_id):
    consulta = Consulta.query.get_or_404(consulta_id)
    if consulta.profissional_id != current_user.id:
        flash('Você não tem permissão para finalizar este atendimento.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    consulta.status = 'FINALIZADA'
    consulta.data_fim = datetime.datetime.utcnow()
    consulta.resumo_atendimento = request.form.get('resumo_atendimento', 'Atendimento finalizado.')
    paciente = Paciente.query.get(consulta.paciente_id)
    paciente.status = 'FINALIZADO'
    db.session.commit()
    flash(f'Atendimento com {paciente.nome_completo} finalizado com sucesso.', 'success')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/atendimento/transferir/<int:consulta_id>', methods=['POST'])
@login_required
def transferir_para_medico(consulta_id):
    consulta = Consulta.query.get_or_404(consulta_id)
    if consulta.profissional_id != current_user.id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    consulta.status = 'TRANSFERIDO'
    consulta.data_fim = datetime.datetime.utcnow()
    consulta.resumo_atendimento = request.form.get('motivo_transferencia', 'Transferido para avaliação médica.')
    paciente = Paciente.query.get(consulta.paciente_id)
    paciente.status = 'AGUARDANDO_MEDICO'
    db.session.commit()
    flash(f'Paciente {paciente.nome_completo} transferido para a fila médica.', 'info')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/atendimento/iniciar_agendado/<int:consulta_id>', methods=['POST'])
@login_required
def iniciar_atendimento_agendado(consulta_id):
    atendimento_existente = Consulta.query.filter_by(profissional_id=current_user.id, status='INICIADA').first()
    if atendimento_existente:
        flash('Você já possui um atendimento em andamento. Finalize-o antes de iniciar um agendado.', 'warning')
        return redirect(url_for('gestor.dashboard'))
    consulta = Consulta.query.get_or_404(consulta_id)
    if consulta.profissional_id != current_user.id or consulta.status != 'AGENDADA':
        flash('Não foi possível iniciar este atendimento.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    consulta.status = 'INICIADA'
    paciente = Paciente.query.get(consulta.paciente_id)
    paciente.status = 'EM_ATENDIMENTO'

    # Gatilho de Log de Uso
    log = LogUso(
        event_type='CONSULTA_AGENDADA_INICIADA',
        unit='consulta',
        related_consulta_id=consulta.id,
        related_usuario_id=current_user.id
    )
    db.session.add(log)
    db.session.commit()

    flash(f'Atendimento agendado com {paciente.nome_completo} foi iniciado.', 'success')
    return redirect(url_for('gestor.dashboard'))

# --- ROTAS DE GERENCIAMENTO DE USUÁRIOS ---

@bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def criar_usuario():
    if request.method == 'POST':
        nome = request.form.get('nome_completo')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        if Usuario.query.filter_by(email=email).first():
            flash('Este email já está cadastrado.', 'danger')
            return redirect(url_for('gestor.criar_usuario'))
        novo_usuario = Usuario(nome_completo=nome, email=email, role=role)
        novo_usuario.set_password(password)
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Usuário criado com sucesso!', 'success')
        return redirect(url_for('gestor.dashboard'))
    return render_template('gestor/form_usuario.html', titulo='Criar Novo Usuário')

@bp.route('/usuarios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    if request.method == 'POST':
        usuario.nome_completo = request.form.get('nome_completo')
        usuario.email = request.form.get('email')
        usuario.role = request.form.get('role')
        password = request.form.get('password')
        if password:
            usuario.set_password(password)
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('gestor.dashboard'))
    return render_template('gestor/form_usuario.html', titulo='Editar Usuário', usuario=usuario)

@bp.route('/usuarios/<int:id>/toggle_active', methods=['POST'])
@login_required
@admin_required
def toggle_active_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    if usuario.id == current_user.id:
        flash('Você não pode desativar a si mesmo.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    usuario.is_active = not usuario.is_active
    db.session.commit()
    status = "ativado" if usuario.is_active else "desativado"
    flash(f'Usuário {usuario.nome_completo} foi {status}.', 'info')
    return redirect(url_for('gestor.dashboard'))

# --- ROTAS DE DOCUMENTOS ---

@bp.route('/atendimento/<int:consulta_id>/documentos', methods=['GET'])
@login_required
def pagina_documentos(consulta_id):
    consulta = Consulta.query.get_or_404(consulta_id)
    if consulta.profissional_id != current_user.id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    return render_template('profissional/documentos.html', consulta=consulta)

@bp.route('/atendimento/<int:consulta_id>/documentos/novo_atestado', methods=['POST'])
@login_required
def criar_atestado(consulta_id):
    consulta = Consulta.query.get_or_404(consulta_id)
    if consulta.profissional_id != current_user.id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    dias_afastamento = request.form.get('dias_afastamento')
    cid = request.form.get('cid', '')
    conteudo_atestado = f"Atesto para os devidos fins que o(a) paciente {consulta.paciente.nome_completo}, CPF {consulta.paciente.cpf}, necessita de {dias_afastamento} dias de afastamento de suas atividades laborais a partir desta data. CID: {cid}"
    novo_documento = Documento(
        consulta_id=consulta.id,
        tipo='ATESTADO',
        conteudo=conteudo_atestado
    )
    db.session.add(novo_documento)
    
    # Gatilho de Log de Uso
    log = LogUso(
        event_type='DOCUMENTO_EMITIDO',
        unit='documento',
        related_consulta_id=consulta.id,
        related_usuario_id=current_user.id
    )
    db.session.add(log)
    db.session.commit()

    flash('Atestado emitido com sucesso!', 'success')
    return redirect(url_for('gestor.pagina_documentos', consulta_id=consulta.id))

# --- ROTAS DE CONFIGURAÇÕES E TAREFAS ---

@bp.route('/configuracoes', methods=['GET', 'POST'])
@login_required
@admin_required
def gerenciar_configuracoes():
    if request.method == 'POST':
        for chave, valor in request.form.items():
            config = Configuracao.query.filter_by(chave=chave).first()
            if config:
                config.valor = valor
            else:
                config = Configuracao(chave=chave, valor=valor)
                db.session.add(config)
        db.session.commit()
        flash('Configurações salvas com sucesso!', 'success')
        return redirect(url_for('gestor.gerenciar_configuracoes'))
    configs_query = Configuracao.query.all()
    configs = {c.chave: c.valor for c in configs_query}
    return render_template('gestor/configuracoes.html', configs=configs)

@bp.route('/tarefas/nova', methods=['POST'])
@login_required
def criar_tarefa():
    if current_user.role != 'PROFISSIONAL_SAUDE':
        flash('Funcionalidade disponível apenas para profissionais de saúde.', 'warning')
        return redirect(url_for('gestor.dashboard'))
    titulo_tarefa = request.form.get('titulo_tarefa')
    if titulo_tarefa:
        nova_tarefa = Tarefa(
            titulo=titulo_tarefa,
            criado_por_id=current_user.id,
            atribuido_para_id=current_user.id
        )
        db.session.add(nova_tarefa)
        db.session.commit()
        flash('Nova tarefa pessoal adicionada.', 'success')
    else:
        flash('O título da tarefa não pode estar vazio.', 'danger')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/tarefas/delegar', methods=['POST'])
@login_required
def delegar_tarefa():
    if current_user.role != 'PROFISSIONAL_SAUDE':
        flash('Funcionalidade disponível apenas para profissionais de saúde.', 'warning')
        return redirect(url_for('gestor.dashboard'))
    titulo = request.form.get('titulo_delegado')
    atribuido_id = request.form.get('atribuido_para_id')
    if titulo and atribuido_id:
        nova_tarefa_delegada = Tarefa(
            titulo=titulo,
            criado_por_id=current_user.id,
            atribuido_para_id=atribuido_id
        )
        db.session.add(nova_tarefa_delegada)
        db.session.commit()
        flash('Tarefa delegada com sucesso!', 'success')
    else:
        flash('Título e destinatário são obrigatórios para delegar uma tarefa.', 'danger')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/tarefas/<int:tarefa_id>/concluir', methods=['POST'])
@login_required
def concluir_tarefa(tarefa_id):
    tarefa = Tarefa.query.get_or_404(tarefa_id)
    if tarefa.atribuido_para_id != current_user.id:
        flash('Acesso negado. Esta tarefa não está atribuída a você.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    tarefa.status = 'CONCLUIDA'
    tarefa.data_conclusao = datetime.datetime.utcnow()
    db.session.commit()
    flash('Tarefa concluída!', 'info')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/chatbot/editor', methods=['GET', 'POST'])
@login_required
@admin_required
def editor_chatbot():
    if request.method == 'POST':
        for chave, texto in request.form.items():
            mensagem = MensagemChatbot.query.filter_by(chave=chave).first()
            if mensagem:
                mensagem.texto = texto
        db.session.commit()
        flash('Mensagens do chatbot atualizadas com sucesso!', 'success')
        return redirect(url_for('gestor.editor_chatbot'))
    mensagens = MensagemChatbot.query.order_by(MensagemChatbot.id).all()
    return render_template('gestor/chatbot_editor.html', mensagens=mensagens)

# --- ROTAS DE AGENDAMENTO ELETIVO ---

@bp.route('/agendamento/novo', methods=['GET'])
@login_required
@admin_required
def agendar_consulta_form():
    pacientes = Paciente.query.order_by(Paciente.nome_completo).all()
    profissionais = Usuario.query.filter_by(role='PROFISSIONAL_SAUDE').order_by(Usuario.nome_completo).all()
    return render_template('gestor/agendamento_form.html', pacientes=pacientes, profissionais=profissionais)

@bp.route('/agendamento/novo', methods=['POST'])
@login_required
@admin_required
def agendar_consulta_submit():
    paciente_id = request.form.get('paciente_id')
    profissional_id = request.form.get('profissional_id')
    data_inicio_str = request.form.get('data_inicio')
    data_inicio = datetime.datetime.fromisoformat(data_inicio_str)
    nova_consulta_agendada = Consulta(
        uuid=str(uuid.uuid4()),
        paciente_id=paciente_id,
        profissional_id=profissional_id,
        status='AGENDADA',
        tipo='ELETIVA',
        data_inicio=data_inicio
    )
    db.session.add(nova_consulta_agendada)
    db.session.commit()
    flash('Consulta eletiva agendada com sucesso!', 'success')
    return redirect(url_for('gestor.dashboard'))

# --- ROTAS PARA GERENCIAMENTO DA BIBLIOTECA DE CONTEÚDOS ---

@bp.route('/biblioteca', methods=['GET'])
@login_required
@admin_required
def biblioteca_index():
    conteudos = BibliotecaConteudo.query.order_by(BibliotecaConteudo.titulo).all()
    return render_template('gestor/biblioteca/index.html', conteudos=conteudos)

@bp.route('/biblioteca/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def biblioteca_novo():
    if request.method == 'POST':
        novo_conteudo = BibliotecaConteudo(
            titulo=request.form.get('titulo'),
            conteudo_texto=request.form.get('conteudo_texto'),
            url_video=request.form.get('url_video'),
            url_imagem=request.form.get('url_imagem'),
            palavras_chave=request.form.get('palavras_chave')
        )
        db.session.add(novo_conteudo)
        db.session.commit()
        flash('Novo conteúdo adicionado à biblioteca com sucesso!', 'success')
        return redirect(url_for('gestor.biblioteca_index'))
    return render_template('gestor/biblioteca/form.html', titulo="Adicionar Novo Conteúdo")

@bp.route('/biblioteca/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def biblioteca_editar(id):
    conteudo = BibliotecaConteudo.query.get_or_404(id)
    if request.method == 'POST':
        conteudo.titulo = request.form.get('titulo')
        conteudo.conteudo_texto = request.form.get('conteudo_texto')
        conteudo.url_video = request.form.get('url_video')
        conteudo.url_imagem = request.form.get('url_imagem')
        conteudo.palavras_chave = request.form.get('palavras_chave')
        db.session.commit()
        flash('Conteúdo atualizado com sucesso!', 'success')
        return redirect(url_for('gestor.biblioteca_index'))
    return render_template('gestor/biblioteca/form.html', titulo="Editar Conteúdo", conteudo=conteudo)

@bp.route('/biblioteca/<int:id>/apagar', methods=['POST'])
@login_required
@admin_required
def biblioteca_apagar(id):
    conteudo = BibliotecaConteudo.query.get_or_404(id)
    db.session.delete(conteudo)
    db.session.commit()
    flash('Conteúdo removido da biblioteca com sucesso.', 'info')
    return redirect(url_for('gestor.biblioteca_index'))

# --- ROTAS PARA PAINEL DE USO ---

@bp.route('/painel_uso')
@login_required
@admin_required
def painel_uso():
    """Exibe um resumo do uso da plataforma."""
    hoje = datetime.date.today()
    inicio_mes = hoje.replace(day=1)
    
    dados_de_uso = db.session.query(
        LogUso.event_type, 
        func.count(LogUso.id)
    ).filter(
        LogUso.timestamp >= inicio_mes
    ).group_by(
        LogUso.event_type
    ).all()
    
    resumo_uso = {
        'CONSULTA_INICIADA': 0,
        'CONSULTA_AGENDADA_INICIADA': 0,
        'DOCUMENTO_EMITIDO': 0
    }
    for event_type, count in dados_de_uso:
        if event_type in resumo_uso:
            resumo_uso[event_type] = count
            
    resumo_uso['TOTAL_CONSULTAS'] = resumo_uso['CONSULTA_INICIADA'] + resumo_uso['CONSULTA_AGENDADA_INICIADA']

    return render_template('gestor/painel_uso.html', resumo=resumo_uso, mes_atual=hoje.strftime('%B de %Y'))