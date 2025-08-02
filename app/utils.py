# Arquivo: app/utils.py

from datetime import datetime
import pytz # Biblioteca para lidar com fusos horários
from .models import Configuracao

def is_servico_aberto(prefeitura_id):
    """
    Verifica se o serviço de atendimento está dentro do horário de funcionamento
    configurado para a prefeitura.
    
    Retorna:
        Uma tupla (bool, str) indicando (status_aberto, mensagem).
    """
    # Define o fuso horário de Brasília
    fuso_horario_brasilia = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_horario_brasilia)
    
    # Nomes dos dias da semana em português para correspondência
    dias_da_semana = [
        "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"
    ]
    dia_atual_str = dias_da_semana[agora.weekday()].lower()

    # Busca as configurações no banco de dados
    configs_query = Configuracao.query.filter_by(prefeitura_id=prefeitura_id).all()
    configs = {c.chave: c.valor for c in configs_query}

    # Pega os valores com um padrão de fallback caso não estejam configurados
    horario_inicio_str = configs.get('HORARIO_INICIO', '08:00')
    horario_fim_str = configs.get('HORARIO_FIM', '18:00')
    dias_funcionamento_str = configs.get('DIAS_FUNCIONAMENTO', 'segunda,terca,quarta,quinta,sexta')
    
    dias_permitidos = [dia.strip().lower() for dia in dias_funcionamento_str.split(',')]

    # 1. Verifica se hoje é um dia de funcionamento
    if dia_atual_str not in dias_permitidos:
        return (False, "FECHADO (Fora do dia de funcionamento)")

    # 2. Verifica se o horário atual está dentro do expediente
    try:
        horario_inicio = datetime.strptime(horario_inicio_str, '%H:%M').time()
        horario_fim = datetime.strptime(horario_fim_str, '%H:%M').time()
        hora_atual = agora.time()

        if not (horario_inicio <= hora_atual < horario_fim):
            return (False, "FECHADO (Fora do horário de expediente)")
            
    except ValueError:
        return (False, "ERRO (Formato de hora inválido nas configurações)")

    # Se passou por todas as verificações, o serviço está aberto
    return (True, "ABERTO")