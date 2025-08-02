# Arquivo: app/gestor/routes.py

from . import bp
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.models import (
    Usuario, Paciente, Consulta, Documento, Configuracao, 
    Tarefa, MensagemChatbot, BibliotecaConteudo, LogUso, LogAcessoPaciente,
    SolicitacaoCorrecao
)
from app.extensions import db
from app.decorators import admin_required
from app.services.video_gateway import VideoGateway
from app.utils import is_servico_aberto

import datetime
import uuid 
from sqlalchemy import func
import csv
import io
import json

@bp.route('/dashboard')
@login_required
def dashboard():
    status_aberto, mensagem_status = is_servico_aberto(current_user.prefeitura_id)
    status_operacional = {'aberto': status_aberto, 'mensagem': mensagem_status}
    
    if current_user.role == 'GESTOR':
        usuarios = Usuario.query.filter_by(prefeitura_id=current_user.prefeitura_id).order_by(Usuario.nome_completo).all()
        return render_template('gestor/dashboard.html', usuarios=usuarios, status_operacional=status_operacional)
    else:
        # Lógica do Profissional
        fila_acolhimento = Paciente.query.filter_by(prefeitura_id=current_user.prefeitura_id, status='AGUARDANDO_ACOLHIMENTO').all()
        fila_medica = Paciente.query.filter_by(prefeitura_id=current_user.prefeitura_id, status='AGUARDANDO_MEDICO').all()
        em_atendimento = Consulta.query.filter_by(prefeitura_id=current_user.prefeitura_id, profissional_id=current_user.id, status='INICIADA').first()
        hoje = datetime.date.today()
        inicio_dia = datetime.datetime.combine(hoje, datetime.time.min)
        fim_dia = datetime.datetime.combine(hoje, datetime.time.max)
        atendimentos_dia = Consulta.query.filter(
            Consulta.prefeitura_id == current_user.prefeitura_id,
            Consulta.profissional_id == current_user.id,
            Consulta.status.in_(['FINALIZADA', 'TRANSFERIDO']),
            Consulta.data_fim.between(inicio_dia, fim_dia)
        ).order_by(Consulta.data_fim.desc()).limit(5).all()
        agenda_do_dia = Consulta.query.filter(
            Consulta.prefeitura_id == current_user.prefeitura_id,
            Consulta.profissional_id == current_user.id,
            Consulta.tipo == 'ELETIVA',
            Consulta.status == 'AGENDADA',
            Consulta.data_inicio.between(inicio_dia, fim_dia)
        ).order_by(Consulta.data_inicio.asc()).all()
        tarefas_pendentes = Tarefa.query.filter_by(
            prefeitura_id=current_user.prefeitura_id,
            atribuido_para_id=current_user.id,
            status='PENDENTE'
        ).order_by(Tarefa.data_criacao.asc()).all()
        outros_profissionais = Usuario.query.filter(
            Usuario.prefeitura_id == current_user.prefeitura_id,
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
            outros_profissionais=outros_profissionais,
            status_operacional=status_operacional 
        )

@bp.route('/atendimento/sala/<int:consulta_id>')
@login_required
def sala_atendimento(consulta_id):
    consulta = Consulta.query.filter_by(
        id=consulta_id, 
        prefeitura_id=current_user.prefeitura_id,
        profissional_id=current_user.id,
        status='INICIADA'
    ).first_or_404()
    video_service = VideoGateway(current_app.config)
    dados_da_sala = video_service.criar_sala_teleconsulta(consulta.id)
    return render_template('profissional/sala_atendimento.html', consulta=consulta, dados_sala=dados_da_sala)

@bp.route('/atendimento/iniciar/<int:paciente_id>/<string:tipo_atendimento>', methods=['POST'])
@login_required
def iniciar_atendimento(paciente_id, tipo_atendimento):
    atendimento_existente = Consulta.query.filter_by(prefeitura_id=current_user.prefeitura_id, profissional_id=current_user.id, status='INICIADA').first()
    if atendimento_existente:
        flash('Você já possui um atendimento em andamento. Finalize-o antes de chamar um novo paciente.', 'warning')
        return redirect(url_for('gestor.dashboard'))
    paciente = Paciente.query.filter_by(id=paciente_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    paciente.status = 'EM_ATENDIMENTO'
    nova_consulta = Consulta(
        prefeitura_id=current_user.prefeitura_id, 
        uuid=str(uuid.uuid4()),
        paciente_id=paciente.id,
        profissional_id=current_user.id,
        status='INICIADA',
        tipo=tipo_atendimento,
        data_inicio=datetime.datetime.utcnow()
    )
    db.session.add(nova_consulta)
    log_uso = LogUso(
        prefeitura_id=current_user.prefeitura_id, 
        event_type='CONSULTA_INICIADA',
        unit='consulta',
        related_usuario_id=current_user.id
    )
    db.session.add(log_uso)
    log_acesso = LogAcessoPaciente(
        prefeitura_id=current_user.prefeitura_id,
        usuario_id=current_user.id,
        paciente_id=paciente.id,
        acao=f"INICIOU_ATENDIMENTO ({tipo_atendimento})"
    )
    db.session.add(log_acesso)
    db.session.commit()
    log_uso.related_consulta_id = nova_consulta.id
    log_acesso.consulta_id = nova_consulta.id
    db.session.commit()
    flash(f'Atendimento com {paciente.nome_completo} iniciado.', 'success')
    return redirect(url_for('.sala_atendimento', consulta_id=nova_consulta.id))

@bp.route('/atendimento/finalizar/<int:consulta_id>', methods=['POST'])
@login_required
def finalizar_atendimento(consulta_id):
    consulta = Consulta.query.filter_by(id=consulta_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
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
    consulta = Consulta.query.filter_by(id=consulta_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
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
    atendimento_existente = Consulta.query.filter_by(prefeitura_id=current_user.prefeitura_id, profissional_id=current_user.id, status='INICIADA').first()
    if atendimento_existente:
        flash('Você já possui um atendimento em andamento. Finalize-o antes de iniciar um agendado.', 'warning')
        return redirect(url_for('gestor.dashboard'))
    consulta = Consulta.query.filter_by(id=consulta_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if consulta.profissional_id != current_user.id or consulta.status != 'AGENDADA':
        flash('Não foi possível iniciar este atendimento.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    consulta.status = 'INICIADA'
    paciente = Paciente.query.get(consulta.paciente_id)
    paciente.status = 'EM_ATENDIMENTO'
    log_uso = LogUso(
        prefeitura_id=current_user.prefeitura_id,
        event_type='CONSULTA_AGENDADA_INICIADA',
        unit='consulta',
        related_consulta_id=consulta.id,
        related_usuario_id=current_user.id
    )
    db.session.add(log_uso)
    log_acesso = LogAcessoPaciente(
        prefeitura_id=current_user.prefeitura_id,
        usuario_id=current_user.id,
        paciente_id=paciente.id,
        consulta_id=consulta.id,
        acao="INICIOU_ATENDIMENTO_AGENDADO"
    )
    db.session.add(log_acesso)
    db.session.commit()
    flash(f'Atendimento agendado com {paciente.nome_completo} foi iniciado.', 'success')
    return redirect(url_for('.sala_atendimento', consulta_id=consulta.id))

@bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def criar_usuario():
    if request.method == 'POST':
        nome = request.form.get('nome_completo')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        if Usuario.query.filter_by(email=email, prefeitura_id=current_user.prefeitura_id).first():
            flash('Este email já está cadastrado para esta prefeitura.', 'danger')
            return redirect(url_for('gestor.criar_usuario'))
        novo_usuario = Usuario(
            prefeitura_id=current_user.prefeitura_id, 
            nome_completo=nome, 
            email=email, 
            role=role
        )
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
    usuario = Usuario.query.filter_by(id=id, prefeitura_id=current_user.prefeitura_id).first_or_404()
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
    usuario = Usuario.query.filter_by(id=id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if usuario.id == current_user.id:
        flash('Você não pode desativar a si mesmo.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    usuario.is_active = not usuario.is_active
    db.session.commit()
    status = "ativado" if usuario.is_active else "desativado"
    flash(f'Usuário {usuario.nome_completo} foi {status}.', 'info')
    return redirect(url_for('gestor.dashboard'))

@bp.route('/atendimento/<int:consulta_id>/documentos', methods=['GET'])
@login_required
def pagina_documentos(consulta_id):
    consulta = Consulta.query.filter_by(id=consulta_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if consulta.profissional_id != current_user.id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    log_acesso = LogAcessoPaciente(
        prefeitura_id=current_user.prefeitura_id,
        usuario_id=current_user.id,
        paciente_id=consulta.paciente_id,
        consulta_id=consulta.id,
        acao="ACESSOU_PAGINA_DOCUMENTOS"
    )
    db.session.add(log_acesso)
    db.session.commit()
    return render_template('profissional/documentos.html', consulta=consulta)

@bp.route('/atendimento/<int:consulta_id>/documentos/novo_atestado', methods=['POST'])
@login_required
def criar_atestado(consulta_id):
    consulta = Consulta.query.filter_by(id=consulta_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if consulta.profissional_id != current_user.id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    dias_afastamento = request.form.get('dias_afastamento')
    cid = request.form.get('cid', '')
    conteudo_atestado = f"Atesto para os devidos fins que o(a) paciente {consulta.paciente.nome_completo}, CPF {consulta.paciente.cpf}, necessita de {dias_afastamento} dias de afastamento de suas atividades laborais a partir desta data. CID: {cid}"
    novo_documento = Documento(
        prefeitura_id=current_user.prefeitura_id,
        consulta_id=consulta.id,
        tipo='ATESTADO',
        conteudo=conteudo_atestado
    )
    db.session.add(novo_documento)
    log_uso = LogUso(
        prefeitura_id=current_user.prefeitura_id,
        event_type='DOCUMENTO_EMITIDO',
        unit='documento',
        related_consulta_id=consulta.id,
        related_usuario_id=current_user.id
    )
    db.session.add(log_uso)
    db.session.commit()
    flash('Atestado emitido com sucesso!', 'success')
    return redirect(url_for('gestor.pagina_documentos', consulta_id=consulta.id))

@bp.route('/configuracoes', methods=['GET', 'POST'])
@login_required
@admin_required
def gerenciar_configuracoes():
    if request.method == 'POST':
        for chave, valor in request.form.items():
            config = Configuracao.query.filter_by(chave=chave, prefeitura_id=current_user.prefeitura_id).first()
            if config:
                config.valor = valor
            else:
                config = Configuracao(
                    prefeitura_id=current_user.prefeitura_id, 
                    chave=chave, 
                    valor=valor
                )
                db.session.add(config)
        db.session.commit()
        flash('Configurações salvas com sucesso!', 'success')
        return redirect(url_for('gestor.gerenciar_configuracoes'))
    configs_query = Configuracao.query.filter_by(prefeitura_id=current_user.prefeitura_id).all()
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
            prefeitura_id=current_user.prefeitura_id,
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
            prefeitura_id=current_user.prefeitura_id,
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
    tarefa = Tarefa.query.filter_by(id=tarefa_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if tarefa.atribuido_para_id != current_user.id:
        flash('Acesso negado. Esta tarefa não está atribuída a você.', 'danger')
        return redirect(url_for('gestor.dashboard'))
    tarefa.status = 'CONCLUIDA'
    tarefa.data_conclusao = datetime.datetime.utcnow()
    db.session.commit()
    flash('Tarefa concluída!', 'info')
    return redirect(url_for('gestor.dashboard'))

# --- ROTA DO EDITOR DE CHATBOT CORRIGIDA E FINAL ---
@bp.route('/chatbot/editor', methods=['GET', 'POST'])
@login_required
@admin_required
def editor_chatbot():
    config_fluxo = Configuracao.query.filter_by(
        chave='CHATBOT_FLOW_JSON',
        prefeitura_id=current_user.prefeitura_id
    ).first()

    if request.method == 'POST':
        flow_json_str = request.form.get('flow_definition')
        if config_fluxo:
            config_fluxo.valor = flow_json_str
        else:
            config_fluxo = Configuracao(
                chave='CHATBOT_FLOW_JSON',
                valor=flow_json_str,
                prefeitura_id=current_user.prefeitura_id,
                descricao='Definição do fluxo do chatbot em formato JSON.'
            )
            db.session.add(config_fluxo)

        for chave, texto in request.form.items():
            if chave.startswith('text_'):
                msg_chave = chave.split('text_')[1]
                mensagem = MensagemChatbot.query.filter_by(chave=msg_chave, prefeitura_id=current_user.prefeitura_id).first()
                if mensagem:
                    mensagem.texto = texto
        
        db.session.commit()
        flash('Fluxo do chatbot salvo com sucesso!', 'success')
        return redirect(url_for('gestor.editor_chatbot'))

    mensagens = MensagemChatbot.query.filter_by(prefeitura_id=current_user.prefeitura_id).all()
    mensagens_dict = {msg.chave: msg.to_dict() for msg in mensagens}
    
    flow_data = {}
    if config_fluxo and config_fluxo.valor:
        try:
            flow_data = json.loads(config_fluxo.valor)
        except json.JSONDecodeError:
            flash('Erro ao carregar a estrutura do fluxo. Usando estrutura padrão.', 'warning')
    
    if not flow_data:
        flow_data = {
            "start_node": "boas_vindas",
            "nodes": {
                "boas_vindas": {"message_key": "msg_bem_vindo_geral", "type": "static", "next_node": "menu_principal"},
                "menu_principal": {"message_key": "msg_menu_principal", "type": "options", "options": []}
            }
        }

    return render_template(
        'gestor/chatbot_editor.html', 
        mensagens=mensagens_dict, 
        flow_data=flow_data
    )

@bp.route('/agendamento/novo', methods=['GET'])
@login_required
@admin_required
def agendar_consulta_form():
    pacientes = Paciente.query.filter_by(prefeitura_id=current_user.prefeitura_id).order_by(Paciente.nome_completo).all()
    profissionais = Usuario.query.filter_by(prefeitura_id=current_user.prefeitura_id, role='PROFISSIONAL_SAUDE').order_by(Usuario.nome_completo).all()
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
        prefeitura_id=current_user.prefeitura_id,
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

@bp.route('/biblioteca', methods=['GET'])
@login_required
@admin_required
def biblioteca_index():
    conteudos = BibliotecaConteudo.query.filter_by(prefeitura_id=current_user.prefeitura_id).order_by(BibliotecaConteudo.titulo).all()
    return render_template('gestor/biblioteca/index.html', conteudos=conteudos)

@bp.route('/biblioteca/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def biblioteca_novo():
    if request.method == 'POST':
        novo_conteudo = BibliotecaConteudo(
            prefeitura_id=current_user.prefeitura_id,
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
    conteudo = BibliotecaConteudo.query.filter_by(id=id, prefeitura_id=current_user.prefeitura_id).first_or_404()
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
    conteudo = BibliotecaConteudo.query.filter_by(id=id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    db.session.delete(conteudo)
    db.session.commit()
    flash('Conteúdo removido da biblioteca com sucesso.', 'info')
    return redirect(url_for('gestor.biblioteca_index'))

@bp.route('/painel_uso')
@login_required
@admin_required
def painel_uso():
    hoje = datetime.date.today()
    inicio_mes = hoje.replace(day=1)
    dados_de_uso = db.session.query(
        LogUso.event_type, 
        func.count(LogUso.id)
    ).filter(
        LogUso.prefeitura_id == current_user.prefeitura_id, 
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

@bp.route('/solicitacoes_correcao')
@login_required
@admin_required
def solicitacoes_correcao():
    solicitacoes = SolicitacaoCorrecao.query.filter_by(
        prefeitura_id=current_user.prefeitura_id,
        status='PENDENTE'
    ).order_by(SolicitacaoCorrecao.timestamp.asc()).all()
    return render_template('gestor/solicitacoes_correcao.html', solicitacoes=solicitacoes)

@bp.route('/solicitacoes-correcao/<int:solicitacao_id>/aprovar', methods=['POST'])
@login_required
@admin_required
def aprovar_correcao(solicitacao_id):
    solicitacao = SolicitacaoCorrecao.query.filter_by(id=solicitacao_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if solicitacao.status != 'PENDENTE':
        flash('Esta solicitação já foi analisada.', 'warning')
        return redirect(url_for('.solicitacoes_correcao'))
    paciente = Paciente.query.get(solicitacao.paciente_id)
    campo_a_corrigir = solicitacao.campo
    novo_valor = solicitacao.justificativa
    if hasattr(paciente, campo_a_corrigir):
        setattr(paciente, campo_a_corrigir, novo_valor)
    solicitacao.status = 'APROVADO'
    solicitacao.analisado_por_id = current_user.id
    solicitacao.data_analise = datetime.datetime.utcnow()
    solicitacao.resposta_gestor = 'Aprovado e alterado no sistema.'
    db.session.commit()
    flash(f'Solicitação para o paciente {paciente.nome_completo} aprovada com sucesso!', 'success')
    return redirect(url_for('.solicitacoes_correcao'))

@bp.route('/solicitacoes-correcao/<int:solicitacao_id>/rejeitar', methods=['POST'])
@login_required
@admin_required
def rejeitar_correcao(solicitacao_id):
    solicitacao = SolicitacaoCorrecao.query.filter_by(id=solicitacao_id, prefeitura_id=current_user.prefeitura_id).first_or_404()
    if solicitacao.status != 'PENDENTE':
        flash('Esta solicitação já foi analisada.', 'warning')
        return redirect(url_for('.solicitacoes_correcao'))
    resposta = request.form.get('resposta_gestor')
    if not resposta:
        flash('O motivo da rejeição é obrigatório.', 'danger')
        return redirect(url_for('.solicitacoes_correcao'))
    solicitacao.status = 'REJEITADO'
    solicitacao.analisado_por_id = current_user.id
    solicitacao.data_analise = datetime.datetime.utcnow()
    solicitacao.resposta_gestor = resposta
    db.session.commit()
    flash('Solicitação rejeitada com sucesso.', 'info')
    return redirect(url_for('.solicitacoes_correcao'))
    
@bp.route('/relatorio-esus')
@login_required
@admin_required
def relatorio_esus():
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    atendimentos = []
    if data_inicio_str and data_fim_str:
        try:
            data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            inicio_dia = datetime.datetime.combine(data_inicio, datetime.time.min)
            fim_dia = datetime.datetime.combine(data_fim, datetime.time.max)
            atendimentos = Consulta.query.filter(
                Consulta.prefeitura_id == current_user.prefeitura_id,
                Consulta.status.in_(['FINALIZADA', 'TRANSFERIDO']),
                Consulta.data_inicio.between(inicio_dia, fim_dia)
            ).order_by(Consulta.data_inicio.asc()).all()
        except ValueError:
            flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
    return render_template('gestor/relatorio_esus.html', atendimentos=atendimentos)

@bp.route('/importar-pacientes', methods=['GET', 'POST'])
@login_required
@admin_required
def importar_pacientes_form():
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('Nenhum arquivo selecionado.', 'danger')
            return redirect(request.url)
        file = request.files['csv_file']
        if file.filename == '':
            flash('Nenhum arquivo selecionado.', 'danger')
            return redirect(request.url)
        if file and file.filename.endswith('.csv'):
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_reader = csv.DictReader(stream)
                pacientes_importados = 0
                erros = []
                for row in csv_reader:
                    cpf = row.get('cpf', '').strip()
                    if not cpf:
                        erros.append(f"Linha ignorada por falta de CPF: {row}")
                        continue
                    paciente_existente = Paciente.query.filter_by(
                        cpf=cpf, 
                        prefeitura_id=current_user.prefeitura_id
                    ).first()
                    if not paciente_existente:
                        novo_paciente = Paciente(
                            prefeitura_id=current_user.prefeitura_id,
                            nome_completo=row.get('nome_completo', '').strip(),
                            cpf=cpf,
                            cns=row.get('cns', '').strip() or None,
                            telefone_whatsapp=row.get('telefone_whatsapp', '').strip()
                        )
                        db.session.add(novo_paciente)
                        pacientes_importados += 1
                db.session.commit()
                flash(f'{pacientes_importados} pacientes foram importados com sucesso!', 'success')
                if erros:
                    flash(f'Ocorreram {len(erros)} erros ou linhas foram ignoradas.', 'warning')
                return redirect(url_for('.importar_pacientes_form'))
            except Exception as e:
                db.session.rollback()
                flash(f'Ocorreu um erro ao processar o arquivo: {e}', 'danger')
                return redirect(request.url)
        else:
            flash('Formato de arquivo inválido. Por favor, envie um arquivo .csv.', 'danger')
            return redirect(request.url)
    return render_template('gestor/importar_pacientes.html')