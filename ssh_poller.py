import time
import threading
from queue import Queue
import paramiko
import os

# Constantes para mensagens da fila
MSG_TYPE_LOG = "LOG"
MSG_TYPE_STATUS = "STATUS"
MSG_TYPE_ERROR = "ERROR"

class SSHLogPoller(threading.Thread):
    """
    Uma thread que monitora (polla) um arquivo de log em um servidor SSH
    e envia novas linhas para uma fila (Queue) de forma thread-safe.
    """

    def __init__(self, config: dict, remote_log_path: str, output_queue: Queue, poll_interval: int = 3):
        super().__init__(daemon=True)
        
        # Configurações
        self.ssh_host = config.get('host')
        self.ssh_user = config.get('user')
        self.ssh_password = config.get('password')
        self.ssh_port = config.get('port', 22)
        self.remote_log_path = remote_log_path
        
        self.output_queue = output_queue
        self.poll_interval = poll_interval
        
        # Controle
        self._stop_event = threading.Event()
        self.current_size = 0
        self.ssh = None
        self.sftp = None

    def _send_to_queue(self, msg_type: str, message: str):
        """Envia dados para a fila de forma padronizada."""
        try:
            self.output_queue.put_nowait((msg_type, message))
        except Exception as e:
            print(f"Erro ao enviar para a fila: {e}")

    def _connect(self) -> bool:
        """Estabelece a conexão SSH."""
        self._send_to_queue(MSG_TYPE_STATUS, f"Conectando via SSH a {self.ssh_host}:{self.ssh_port}...")
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_password,
                timeout=10
            )
            self.sftp = self.ssh.open_sftp()
            self._send_to_queue(MSG_TYPE_STATUS, f"Conectado via SSH como {self.ssh_user}.")
            return True
        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Falha na conexão SSH: {e}")
            self.ssh = None
            self.sftp = None
            return False

    def _get_remote_size(self) -> int:
        """Obtém o tamanho do arquivo de log remoto via SSH."""
        if not self.sftp:
            if not self._connect():
                return -1

        try:
            stat = self.sftp.stat(self.remote_log_path)
            return stat.st_size
        except FileNotFoundError:
            self._send_to_queue(MSG_TYPE_ERROR, f"Arquivo não encontrado: {self.remote_log_path}")
            return -1
        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro ao obter tamanho do arquivo: {e}")
            self._disconnect()
            return -1

    def _fetch_new_data(self):
        """Busca apenas os dados novos do arquivo (usando offset)."""
        if not self.sftp:
            self._send_to_queue(MSG_TYPE_ERROR, "Desconectado. Tentando reconectar...")
            if not self._connect():
                return

        self._send_to_queue(MSG_TYPE_STATUS, f"Buscando novos dados (a partir de {self.current_size} bytes)...")
        
        try:
            with self.sftp.open(self.remote_log_path, 'rb') as remote_file:
                remote_file.seek(self.current_size)
                new_data = remote_file.read()
                
                if not new_data:
                    self._send_to_queue(MSG_TYPE_STATUS, "Verificação concluída. Sem dados novos.")
                    return

                try:
                    text_data = new_data.decode('utf-8', errors='ignore')
                except UnicodeDecodeError:
                    text_data = new_data.decode('latin-1', errors='ignore')

                for line in text_data.splitlines():
                    if line:
                        self._send_to_queue(MSG_TYPE_LOG, line)
                
                self._send_to_queue(MSG_TYPE_STATUS, "Novos dados processados.")

        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro ao ler arquivo: {e}")
            self._disconnect()

    def _disconnect(self):
        """Fecha a conexão SSH se estiver ativa."""
        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
            finally:
                self.sftp = None
        
        if self.ssh:
            try:
                self.ssh.close()
                self._send_to_queue(MSG_TYPE_STATUS, "Conexão SSH fechada.")
            except Exception as e:
                self._send_to_queue(MSG_TYPE_STATUS, f"Erro ao fechar SSH: {e}")
            finally:
                self.ssh = None

    def run(self):
        """O loop principal da thread de monitoramento."""
        self._send_to_queue(MSG_TYPE_STATUS, f"Iniciando monitoramento SSH para: {self.remote_log_path}")
        
        initial_size = self._get_remote_size()
        
        if initial_size == -1:
            self._send_to_queue(MSG_TYPE_ERROR, "Falha ao obter tamanho inicial.")
        else:
            self.current_size = initial_size
            self._send_to_queue(MSG_TYPE_STATUS, f"Monitoramento SSH iniciado. Tamanho atual: {self.current_size} bytes.")
            self._send_to_queue(MSG_TYPE_LOG, "--- [ Monitoramento SSH iniciado - Aguardando novos dados ] ---")

        while not self._stop_event.is_set():
            try:
                new_size = self._get_remote_size()

                if new_size == -1:
                    self._send_to_queue(MSG_TYPE_ERROR, "Aguardando reconexão...")
                
                elif new_size > self.current_size:
                    self._send_to_queue(MSG_TYPE_STATUS, f"Arquivo cresceu. Novo tamanho: {new_size} bytes.")
                    self._fetch_new_data()
                    self.current_size = new_size
                
                elif new_size < self.current_size:
                    self._send_to_queue(MSG_TYPE_STATUS, "!!! Rotação de log detectada (arquivo diminuiu) !!!")
                    self._send_to_queue(MSG_TYPE_LOG, f"--- [ Rotação de log detectada - Lendo do início (Novo tamanho: {new_size}) ] ---")
                    self.current_size = 0
                    self._fetch_new_data()
                    self.current_size = new_size

            except Exception as e:
                self._send_to_queue(MSG_TYPE_ERROR, f"Erro inesperado no loop: {e}")
                self._disconnect()

            self._stop_event.wait(self.poll_interval)

        self._disconnect()
        self._send_to_queue(MSG_TYPE_STATUS, "Monitoramento SSH parado.")

    def stop(self):
        """Sinaliza para a thread parar."""
        self._send_to_queue(MSG_TYPE_STATUS, "Recebido sinal de parada...")
        self._stop_event.set()