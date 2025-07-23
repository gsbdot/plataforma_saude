# Arquivo: app/models.py

from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(50), nullable=False, default='PROFISSIONAL_SAUDE')
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

class LogUso(db.Model):
    """Modelo para registrar eventos de consumo da plataforma para billing."""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    
    # Tipo do evento: 'CONSULTA_INICIADA', 'DOCUMENTO_EMITIDO', etc.
    event_type = db.Column(db.String(100), nullable=False, index=True)
    
    # Detalhes do evento
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(50)) # Ex: 'consulta', 'documento', 'minuto_video'
    
    # Relacionamentos para auditoria
    related_consulta_id = db.Column(db.Integer, db.ForeignKey('consulta.id'), nullable=True)
    related_usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)

    def __repr__(self):
        return f'<LogUso {self.timestamp} - {self.event_type}>'

    def __repr__(self):
        return f'<Usuario {self.email}>'

class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False, index=True)
    cns = db.Column(db.String(15), unique=True, nullable=True, index=True)
    telefone_whatsapp = db.Column(db.String(20), nullable=False, unique=True)
    status = db.Column(db.String(50), nullable=False, default='AGUARDANDO_ACOLHIMENTO', index=True)
    
    def __repr__(self):
        return f'<Paciente {self.nome_completo}>'

class Consulta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    profissional_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='INICIADA', index=True)
    tipo = db.Column(db.String(50), nullable=False, default='ACOLHIMENTO_ENF')
    data_inicio = db.Column(db.DateTime, nullable=False)
    data_fim = db.Column(db.DateTime)
    resumo_atendimento = db.Column(db.Text)

    paciente = db.relationship('Paciente', backref=db.backref('consultas', lazy=True))
    profissional = db.relationship('Usuario', backref=db.backref('consultas', lazy=True))

class TermoConsentimentoLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(256)) 
    versao_termo = db.Column(db.String(20), nullable=False)
    timestamp_aceite = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    paciente = db.relationship('Paciente', backref=db.backref('logs_consentimento', lazy=True))

    def __repr__(self):
        return f'<Log LGPD para Paciente ID {self.paciente_id} em {self.timestamp_aceite}>'

class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consulta_id = db.Column(db.Integer, db.ForeignKey('consulta.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False, index=True)
    conteudo = db.Column(db.Text, nullable=False)
    data_emissao = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    hash_assinatura = db.Column(db.String(256))
    consulta = db.relationship('Consulta', backref=db.backref('documentos', lazy=True))

    def __repr__(self):
        return f'<Documento {self.tipo} para Consulta ID {self.consulta_id}>'

class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(100), unique=True, nullable=False, index=True)
    valor = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text)

    def __repr__(self):
        return f'<Configuracao {self.chave}={self.valor}>'

class Tarefa(db.Model):
    """Modelo para tarefas dos profissionais de saúde, com delegação."""
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    
    # Chave estrangeira para o usuário que CRIOU a tarefa
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    
    # Chave estrangeira para o usuário a quem a tarefa foi ATRIBUÍDA
    # Pode ser nulo se a tarefa for pessoal (não delegada)
    atribuido_para_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    
    # Status da tarefa: 'PENDENTE' ou 'CONCLUIDA'
    status = db.Column(db.String(50), default='PENDENTE', nullable=False, index=True)
    
    data_criacao = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    
    # Relacionamentos
    criado_por = db.relationship('Usuario', foreign_keys=[criado_por_id], backref=db.backref('tarefas_criadas', lazy='dynamic'))
    atribuido_para = db.relationship('Usuario', foreign_keys=[atribuido_para_id], backref=db.backref('tarefas_atribuidas', lazy='dynamic'))

    def __repr__(self):
        return f'<Tarefa {self.id}: {self.titulo}>'

class MensagemChatbot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(100), unique=True, nullable=False, index=True)
    texto = db.Column(db.Text, nullable=False)
    descricao = db.Column(db.String(255))

    def __repr__(self):
        return f'<MensagemChatbot {self.chave}>'

class BibliotecaConteudo(db.Model):
    """Modelo para o acervo de conteúdos de auto-cuidado."""
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo_texto = db.Column(db.Text, nullable=False)
    
    # Links para mídias externas (ex: vídeos no YouTube, imagens)
    url_video = db.Column(db.String(255))
    url_imagem = db.Column(db.String(255))
    
    # Palavras-chave para facilitar a busca pelo chatbot
    palavras_chave = db.Column(db.String(255)) # Ex: "febre,dor de cabeça,gripe"

    data_criacao = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f'<BibliotecaConteudo {self.titulo}>'