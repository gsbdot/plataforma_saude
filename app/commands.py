# Arquivo: app/commands.py

import click
from flask.cli import with_appcontext
from .extensions import db
from .models import Prefeitura, Usuario, Paciente, Configuracao, MensagemChatbot
import json

@click.command(name="seed-db")
@with_appcontext
def seed_db_command():
    """Cria e corrige dados padrão (prefeitura, gestor, paciente, config do chatbot) para testes."""
    
    prefeitura_padrao = Prefeitura.query.filter_by(subdominio='default').first()
    if not prefeitura_padrao:
        prefeitura_padrao = Prefeitura(nome_cidade='Cidade Padrão', subdominio='default')
        db.session.add(prefeitura_padrao)
        print("Prefeitura 'default' criada com sucesso.")
    
    db.session.flush()

    # ... (código do gestor e paciente permanece o mesmo)
    gestor_padrao = Usuario.query.filter_by(email='gestor@default.com', prefeitura_id=prefeitura_padrao.id).first()
    if not gestor_padrao:
        gestor_padrao = Usuario(
            prefeitura_id=prefeitura_padrao.id, nome_completo='Gestor Padrão',
            email='gestor@default.com', role='GESTOR', is_active=True
        )
        gestor_padrao.set_password('1234')
        db.session.add(gestor_padrao)
        print("Usuário 'gestor@default.com' criado com sucesso.")

    paciente_teste = Paciente.query.filter_by(cpf='11122233344', prefeitura_id=prefeitura_padrao.id).first()
    if not paciente_teste:
        paciente_teste = Paciente(
            prefeitura_id=prefeitura_padrao.id, nome_completo='Maria da Silva (Paciente Teste)',
            cpf='11122233344', cns='980016293300003', telefone_whatsapp='+5511999998888'
        )
        db.session.add(paciente_teste)
        print("Paciente de teste 'Maria da Silva' criado com sucesso.")
        
    # --- CORREÇÃO E ATUALIZAÇÃO DO FLUXO DO CHATBOT ---
    
    # 1. Deleta configurações antigas para garantir um estado limpo
    Configuracao.query.filter_by(chave='CHATBOT_FLOW_DEFINITION', prefeitura_id=prefeitura_padrao.id).delete()
    Configuracao.query.filter_by(chave='CHATBOT_FLOW_JSON', prefeitura_id=prefeitura_padrao.id).delete()
    print("Configurações antigas do chatbot removidas.")

    # 2. Define a nova estrutura padrão em JSON
    fluxo_padrao_dict = {
        "start_node": "boas_vindas",
        "nodes": {
            "boas_vindas": {
                "message_key": "msg_bem_vindo_geral", "type": "static", "next_node": "menu_principal"
            },
            "menu_principal": {
                "message_key": "msg_menu_principal", "type": "options",
                "options": [
                    {"label": "Falar com Enfermagem", "next_node": "fila_acolhimento"},
                    {"label": "Falar com Médico", "next_node": "fila_medico"}
                ]
            },
            "fila_acolhimento": {
                "message_key": "msg_fila_acolhimento", "type": "action",
                "action": "JOIN_QUEUE", "queue": "ACOLHIMENTO_ENF"
            },
            "fila_medico": {
                "message_key": "msg_fila_medico", "type": "action",
                "action": "JOIN_QUEUE", "queue": "CONSULTA_MEDICA"
            }
        }
    }
    
    nova_config = Configuracao(
        prefeitura_id=prefeitura_padrao.id,
        chave='CHATBOT_FLOW_JSON',
        valor=json.dumps(fluxo_padrao_dict, indent=4),
        descricao='Definição do fluxo do chatbot em formato JSON.'
    )
    db.session.add(nova_config)
    print("Nova definição de fluxo padrão do chatbot (JSON) criada.")

    # 3. Cria as mensagens padrão se não existirem
    mensagens_padrao = {
        "msg_bem_vindo_geral": "Olá! Bem-vindo(a) ao nosso serviço de saúde digital.",
        "msg_menu_principal": "Como podemos ajudar hoje?",
        "msg_fila_acolhimento": "Ok, você está na fila para falar com a enfermagem. Aguarde um momento.",
        "msg_fila_medico": "Certo, você está na fila para falar com um médico. Aguarde um momento."
    }
    for chave, texto in mensagens_padrao.items():
        if not MensagemChatbot.query.filter_by(chave=chave, prefeitura_id=prefeitura_padrao.id).first():
            msg = MensagemChatbot(prefeitura_id=prefeitura_padrao.id, chave=chave, texto=texto, descricao=f"Mensagem para o nó {chave}")
            db.session.add(msg)
    print("Mensagens padrão do chatbot verificadas/criadas.")
    # --- FIM DA CORREÇÃO ---

    db.session.commit()
    print("Banco de dados populado e corrigido com sucesso.")