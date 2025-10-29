import time
from ftplib import FTP, error_perm, error_temp
import threading
from queue import Queue

# Constantes para mensagens da fila
MSG_TYPE_LOG = "LOG"
MSG_TYPE_STATUS = "STATUS"
MSG_TYPE_ERROR = "ERROR"

class FTPLogPoller(threading.Thread):
    """
    Uma thread que monitora (polla) um arquivo de log em um servidor FTP
    e envia novas linhas para uma fila (Queue) de forma thread-safe.
    """

    def __init__(self, config: dict, remote_log_path: str, output_queue: Queue, poll_interval: int = 3):
        super().__init__(daemon=True)
        
        # Configurações
        self.ftp_host = config.get('ftp_host')
        self.ftp_user = config.get('ftp_user')
        self.ftp_password = config.get('ftp_password') # Senha já descriptografada
        self.ftp_port = config.get('ftp_port', 21)
        self.remote_log_path = remote_log_path
        
        self.output_queue = output_queue
        self.poll_interval = poll_interval
        
        # Controle
        self._stop_event = threading.Event()
        self.current_size = 0
        self.ftp = None

    def _send_to_queue(self, msg_type: str, message: str):
        """Envia dados para a fila de forma padronizada."""
        try:
            self.output_queue.put_nowait((msg_type, message))
        except Exception as e:
            # A fila pode estar cheia se a UI travar, mas é raro
            print(f"Erro ao enviar para a fila: {e}")

    def _connect(self) -> bool:
        """Estabelece a conexão FTP e define o modo passivo."""
        self._send_to_queue(MSG_TYPE_STATUS, f"Conectando a {self.ftp_host}:{self.ftp_port}...")
        try:
            self.ftp = FTP()
            self.ftp.connect(self.ftp_host, self.ftp_port, timeout=10)
            self.ftp.login(self.ftp_user, self.ftp_password)
            self.ftp.set_pasv(True) # Modo passivo é essencial
            self._send_to_queue(MSG_TYPE_STATUS, f"Conectado e autenticado como {self.ftp_user}.")
            return True
        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Falha na conexão FTP: {e}")
            self.ftp = None
            return False

    def _get_remote_size(self) -> int:
        """Obtém o tamanho do arquivo de log remoto."""
        if not self.ftp:
            if not self._connect():
                return -1 # Indica falha na conexão

        try:
            size = self.ftp.size(self.remote_log_path)
            if size is None:
                # Alguns servidores FTP podem não suportar SIZE
                self._send_to_queue(MSG_TYPE_ERROR, "Servidor FTP não suporta o comando SIZE. Tentando 'LIST'.")
                # Fallback: Tentar com LIST (menos eficiente)
                listing = []
                self.ftp.retrlines(f'LIST {self.remote_log_path}', listing.append)
                if listing:
                    # Exemplo de linha: '-rw-r--r-- 1 user group 12345 Oct 29 10:00 debug.log'
                    parts = listing[0].split()
                    if len(parts) >= 5:
                        size = int(parts[4])
                    else:
                         self._send_to_queue(MSG_TYPE_ERROR, "Não foi possível determinar o tamanho do arquivo via LIST.")
                         return -1
                else:
                    self._send_to_queue(MSG_TYPE_ERROR, f"Arquivo não encontrado ou inacessível: {self.remote_log_path}")
                    return -1
            
            return size
        
        except error_perm as e:
            if "550" in str(e): # 550 File not found
                self._send_to_queue(MSG_TYPE_ERROR, f"Arquivo não encontrado no FTP: {self.remote_log_path}")
            else:
                self._send_to_queue(MSG_TYPE_ERROR, f"Erro de permissão FTP (SIZE): {e}")
            return -1
        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro ao obter tamanho do arquivo (desconectado?): {e}")
            self._disconnect()
            return -1

    def _fetch_new_data(self):
        """Busca apenas os dados novos do arquivo (usando offset)."""
        if not self.ftp:
            self._send_to_queue(MSG_TYPE_ERROR, "Desconectado. Tentando reconectar...")
            if not self._connect():
                return # Tenta novamente no próximo ciclo

        self._send_to_queue(MSG_TYPE_STATUS, f"Buscando novos dados (a partir de {self.current_size} bytes)...")
        
        # Buffer para coletar os dados binários
        data_chunks = []
        
        try:
            # Usa retrbinary com offset (RETR + REST)
            self.ftp.retrbinary(f'RETR {self.remote_log_path}', data_chunks.append, rest=self.current_size)
            
            if not data_chunks:
                # Isso pode acontecer se o arquivo foi modificado mas não cresceu (raro)
                self._send_to_queue(MSG_TYPE_STATUS, "Verificação concluída. Sem dados novos.")
                return

            # Decodifica os bytes. Ignora erros de decodificação (comum em logs)
            try:
                new_data = b''.join(data_chunks).decode('utf-8', errors='ignore')
            except UnicodeDecodeError as e:
                self._send_to_queue(MSG_TYPE_ERROR, f"Erro de decodificação (UTF-8): {e}. Tentando 'latin-1'...")
                new_data = b''.join(data_chunks).decode('latin-1', errors='ignore') # Fallback comum

            # Envia as linhas de log para a fila
            for line in new_data.splitlines():
                if line: # Evita linhas em branco
                    self._send_to_queue(MSG_TYPE_LOG, line)
            
            self._send_to_queue(MSG_TYPE_STATUS, "Novos dados processados.")

        except error_temp as e:
            # 425: Não pode abrir conexão de dados (problema de firewall/PASV?)
            # 421: Timeout
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro temporário de FTP (RETR): {e}. Tentando reconectar...")
            self._disconnect()
        except error_perm as e:
            # 550: File not found (pode ter sido rotacionado/excluído)
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro de permissão FTP (RETR) ou arquivo não encontrado: {e}")
            self.current_size = 0 # Reseta o tamanho
            self._disconnect()
        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro inesperado (RETR): {e}")
            self._disconnect()

    def _disconnect(self):
        """Fecha a conexão FTP se estiver ativa."""
        if self.ftp:
            try:
                self.ftp.quit()
                self._send_to_queue(MSG_TYPE_STATUS, "Conexão FTP fechada.")
            except Exception as e:
                # Ignora erros ao fechar (ex: conexão já caiu)
                self._send_to_queue(MSG_TYPE_STATUS, f"Erro ao fechar FTP (pode já estar fechada): {e}")
            finally:
                self.ftp = None

    def run(self):
        """O loop principal da thread de monitoramento."""
        self._send_to_queue(MSG_TYPE_STATUS, f"Iniciando monitoramento para: {self.remote_log_path}")
        
        # Tenta obter o tamanho inicial
        initial_size = self._get_remote_size()
        if initial_size == -1:
            self._send_to_queue(MSG_TYPE_ERROR, "Falha ao obter tamanho inicial. Verifique o caminho e permissões.")
            # A thread continua tentando se conectar
        else:
            # Define o tamanho inicial para começar do fim
            self.current_size = initial_size
            self._send_to_queue(MSG_TYPE_STATUS, f"Monitoramento iniciado. Tamanho atual: {self.current_size} bytes.")
            self._send_to_queue(MSG_TYPE_LOG, "--- [ Monitoramento iniciado - Aguardando novos dados ] ---")

        while not self._stop_event.is_set():
            try:
                new_size = self._get_remote_size()

                if new_size == -1:
                    # Erro de conexão ou arquivo não encontrado, pausa e tenta reconectar
                    self._send_to_queue(MSG_TYPE_ERROR, "Aguardando reconexão...")
                
                elif new_size > self.current_size:
                    # Arquivo cresceu, busca novos dados
                    self._send_to_queue(MSG_TYPE_STATUS, f"Arquivo cresceu. Novo tamanho: {new_size} bytes.")
                    self._fetch_new_data()
                    self.current_size = new_size # Atualiza o tamanho
                
                elif new_size < self.current_size:
                    # Rotação de log (arquivo foi truncado ou substituído)
                    self._send_to_queue(MSG_TYPE_STATUS, "!!! Rotação de log detectada (arquivo diminuiu) !!!")
                    self._send_to_queue(MSG_TYPE_LOG, f"--- [ Rotação de log detectada - Lendo do início (Novo tamanho: {new_size}) ] ---")
                    self.current_size = 0 # Reseta para ler do início
                    self._fetch_new_data() # Busca os dados (agora do início)
                    self.current_size = new_size # Atualiza o novo tamanho
                
                # else: new_size == self.current_size (sem mudanças)

            except Exception as e:
                # Captura geral para evitar que a thread morra
                self._send_to_queue(MSG_TYPE_ERROR, f"Erro inesperado no loop: {e}")
                self._disconnect()

            # Aguarda o intervalo de polling, mas checa o evento de parada
            self._stop_event.wait(self.poll_interval)

        # Loop encerrado (stop() foi chamado)
        self._disconnect()
        self._send_to_queue(MSG_TYPE_STATUS, "Monitoramento parado.")

    def stop(self):
        """Sinaliza para a thread parar."""
        self._send_to_queue(MSG_TYPE_STATUS, "Recebido sinal de parada...")
        self._stop_event.set()