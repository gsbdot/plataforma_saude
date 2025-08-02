# Arquivo: app/models.py

from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime

class Prefeitura(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_cidade = db.Column(db.String(120), nullable=False, unique=True)
    subdominio = db.Column(db.String(120), nullable=False, unique=True, index=True)
    status_assinatura = db.Column(db.String(50), nullable=False, default='ATIVA')
    limite_consultas_mes = db.Column(db.Integer, default=1000)
    limite_atendimentos_mes = db.Column(db.Integer, default=2000)
    limite_usuarios_profissionais = db.Column(db.Integer, default=50)

    def __repr__(self):
        return f'<Prefeitura {self.nome_cidade}>'

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    nome_completo = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(50), nullable=False, default='PROFISSIONAL_SAUDE')
    is_active = db.Column(db.Boolean, default=True)
    prefeitura = db.relationship('Prefeitura', backref=db.backref('usuarios', lazy=True))
    __table_args__ = (db.UniqueConstraint('email', 'prefeitura_id', name='_email_prefeitura_uc'),)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)
        
    def __repr__(self):
        return f'<Usuario {self.email}>'

class LogUso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False, index=True)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(50))
    related_consulta_id = db.Column(db.Integer, db.ForeignKey('consulta.id'), nullable=True)
    related_usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)

    def __repr__(self):
        return f'<LogUso {self.timestamp} - {self.event_type}>'

class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    nome_completo = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(11), nullable=False, index=True)
    cns = db.Column(db.String(15), nullable=True, index=True)
    telefone_whatsapp = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='AGUARDANDO_ACOLHIMENTO', index=True)
    prefeitura = db.relationship('Prefeitura', backref=db.backref('pacientes', lazy=True))
    __table_args__ = (
        db.UniqueConstraint('cpf', 'prefeitura_id', name='_cpf_prefeitura_uc'),
        db.UniqueConstraint('telefone_whatsapp', 'prefeitura_id', name='_telefone_prefeitura_uc'),
    )

    def __repr__(self):
        return f'<Paciente {self.nome_completo}>'

class Consulta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
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
    prefeitura = db.relationship('Prefeitura', backref=db.backref('consultas', lazy=True))

class TermoConsentimentoLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
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
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
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
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    chave = db.Column(db.String(100), nullable=False, index=True)
    valor = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint('chave', 'prefeitura_id', name='_chave_prefeitura_uc'),)

    def __repr__(self):
        return f'<Configuracao {self.chave}={self.valor}>'

class Tarefa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    atribuido_para_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    status = db.Column(db.String(50), default='PENDENTE', nullable=False, index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    criado_por = db.relationship('Usuario', foreign_keys=[criado_por_id], backref=db.backref('tarefas_criadas', lazy='dynamic'))
    atribuido_para = db.relationship('Usuario', foreign_keys=[atribuido_para_id], backref=db.backref('tarefas_atribuidas', lazy='dynamic'))

    def __repr__(self):
        return f'<Tarefa {self.id}: {self.titulo}>'

class MensagemChatbot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    chave = db.Column(db.String(100), nullable=False, index=True)
    texto = db.Column(db.Text, nullable=False)
    descricao = db.Column(db.String(255))
    __table_args__ = (db.UniqueConstraint('chave', 'prefeitura_id', name='_msg_chatbot_chave_prefeitura_uc'),)

    def __repr__(self):
        return f'<MensagemChatbot {self.chave}>'

    # --- FUNÇÃO ADICIONADA ---
    def to_dict(self):
        """Converte o objeto para um dicionário, útil para JSON."""
        return {
            'id': self.id,
            'chave': self.chave,
            'texto': self.texto,
            'descricao': self.descricao
        }
    # --- FIM DA ADIÇÃO ---

class BibliotecaConteudo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo_texto = db.Column(db.Text, nullable=False)
    url_video = db.Column(db.String(255))
    url_imagem = db.Column(db.String(255))
    palavras_chave = db.Column(db.String(255))
    data_criacao = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f'<BibliotecaConteudo {self.titulo}>'

class LogAcessoPaciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False, index=True)
    consulta_id = db.Column(db.Integer, db.ForeignKey('consulta.id'), nullable=True)
    acao = db.Column(db.String(255), nullable=False)
    usuario = db.relationship('Usuario', backref='logs_de_acesso')
    paciente = db.relationship('Paciente', backref='logs_de_acesso_recebidos')

    def __repr__(self):
        return f'<LogAcesso: Usuario {self.usuario_id} acessou Paciente {self.paciente_id} em {self.timestamp}>'

class MagicLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    expira_em = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)
    paciente = db.relationship('Paciente', backref='magic_links')

    def __repr__(self):
        return f'<MagicLink para Paciente ID {self.paciente_id}>'
        
class SolicitacaoCorrecao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    prefeitura_id = db.Column(db.Integer, db.ForeignKey('prefeitura.id'), nullable=False)
    campo = db.Column(db.String(100), nullable=False)
    justificativa = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='PENDENTE', nullable=False, index=True)
    analisado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    data_analise = db.Column(db.DateTime, nullable=True)
    resposta_gestor = db.Column(db.Text, nullable=True)
    paciente = db.relationship('Paciente', backref='solicitacoes_correcao')