# app/services/messaging_gateway.py

class MessagingGateway:
    """
    Interface para o provedor de serviços de mensageria (ex: WhatsApp).
    """
    def __init__(self, app_config):
        self.config = app_config
        # Ex: self.auth_token = app_config.get('TWILIO_AUTH_TOKEN')
        print("Gateway de Mensageria Inicializado.")

    def enviar_mensagem(self, telefone_destino, mensagem):
        """
        Envia uma mensagem de texto para o destinatário.
        """
        # --- CORREÇÃO: Removidas as aspas simples ao redor de {mensagem} ---
        print(f"Enviando mensagem para {telefone_destino}: {mensagem}")
        # ------------------------------------------------------------------
        # A lógica de integração com a API de WhatsApp virá aqui.
        return {'status': 'sucesso', 'id_mensagem': 'msg_exemplo_abcde'}