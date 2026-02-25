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
        
        # --- (NOVO) Controle de Reconexão Automática ---
        self.max_reconnect_attempts = 10  # Máximo de tentativas
        self.reconnect_delay_base = 5     # Delay base em segundos
        self.reconnect_attempts = 0       # Contador de tentativas

    def _send_to_queue(self, msg_type: str, message: str):
        """Envia dados para a fila de forma padronizada."""
        try:
            self.output_queue.put_nowait((msg_type, message))
        except Exception as e:
            print(f"Erro ao enviar para a fila: {e}")

    def _connect(self) -> bool:
        """Estabelece a conexão FTP e define o modo passivo."""
        self._send_to_queue(MSG_TYPE_STATUS, f"Conectando a {self.ftp_host}:{self.ftp_port}...")
        try:
            self.ftp = FTP()
            self.ftp.connect(self.ftp_host, self.ftp_port, timeout=10)
            self.ftp.login(self.ftp_user, self.ftp_password)
            self.ftp.set_pasv(True) 
            self._send_to_queue(MSG_TYPE_STATUS, f"Conectado e autenticado como {self.ftp_user}.")
            return True
        except Exception as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Falha na conexão FTP: {e}")
            self.ftp = None
            return False

    def _get_remote_size(self) -> int:
        """
        Obtém o tamanho do arquivo de log remoto.
        CORRIGIDO: Tenta SIZE, e se falhar (permissão 5xx), 
        tenta o fallback com LIST.
        """
        if not self.ftp:
            if not self._connect():
                return -1 

        size = None
        try:
            # --- Primeira Tentativa: Comando SIZE (rápido) ---
            size = self.ftp.size(self.remote_log_path)
            
        except error_perm as e_size:
            # --- Falha no SIZE (5xx): Tentar Fallback ---
            self._send_to_queue(MSG_TYPE_STATUS, f"Comando SIZE falhou ({e_size}). Tentando fallback com LIST...")
        except Exception as e_other:
            # Erro de conexão, etc.
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro ao obter tamanho (desconectado?): {e_other}")
            self._disconnect()
            return -1

        # Se size falhou (error_perm) ou servidor retornou None (não suportado)
        if size is None:
            try:
                # --- Segunda Tentativa: Comando LIST (lento) ---
                listing = []
                # LISTar um arquivo específico
                self.ftp.retrlines(f'LIST {self.remote_log_path}', listing.append)
                
                if listing:
                    # Ex: '-rw-r--r-- 1 user group 12345 Oct 29 10:00 debug.log'
                    parts = listing[0].split()
                    if len(parts) >= 5:
                        try:
                            # Tenta o índice 4 (5º elemento), mais comum
                            size = int(parts[4])
                        except ValueError:
                            size = None # Não era um número
                    
                    if size is None:
                        # Fallback do fallback: Tenta achar o maior número
                        possible_sizes = []
                        for part in parts:
                            if part.isdigit():
                                possible_sizes.append(int(part))
                        if possible_sizes:
                            size = max(possible_sizes) # O tamanho é geralmente o maior
                        else:
                            self._send_to_queue(MSG_TYPE_ERROR, f"Não foi possível extrair o tamanho do arquivo via LIST: {listing[0]}")
                            return -1
                else:
                    self._send_to_queue(MSG_TYPE_ERROR, f"Arquivo não encontrado ou inacessível via LIST: {self.remote_log_path}")
                    return -1
            
            except error_perm as e_list:
                # Se o LIST também falhar com 550
                if "550" in str(e_list): 
                    self._send_to_queue(MSG_TYPE_ERROR, f"Arquivo não encontrado no FTP (LIST falhou): {self.remote_log_path}")
                else:
                    self._send_to_queue(MSG_TYPE_ERROR, f"Erro de permissão FTP (LIST falhou): {e_list}")
                return -1
            except Exception as e:
                self._send_to_queue(MSG_TYPE_ERROR, f"Erro inesperado no fallback (LIST): {e}")
                self._disconnect()
                return -1

        # Se chegamos aqui, ou size (do SIZE) ou size (do LIST) é um número
        try:
            return int(size)
        except (TypeError, ValueError):
            self._send_to_queue(MSG_TYPE_ERROR, f"Tamanho do arquivo inválido recebido: {size}")
            return -1

    def _fetch_new_data(self):
        """Busca apenas os dados novos do arquivo (usando offset)."""
        if not self.ftp:
            self._send_to_queue(MSG_TYPE_ERROR, "Desconectado. Tentando reconectar...")
            if not self._connect():
                return 

        self._send_to_queue(MSG_TYPE_STATUS, f"Buscando novos dados (a partir de {self.current_size} bytes)...")
        
        data_chunks = []
        
        try:
            self.ftp.retrbinary(f'RETR {self.remote_log_path}', data_chunks.append, rest=self.current_size)
            
            if not data_chunks:
                self._send_to_queue(MSG_TYPE_STATUS, "Verificação concluída. Sem dados novos.")
                return

            try:
                new_data = b''.join(data_chunks).decode('utf-8', errors='ignore')
            except UnicodeDecodeError:
                new_data = b''.join(data_chunks).decode('latin-1', errors='ignore') 

            for line in new_data.splitlines():
                if line: 
                    self._send_to_queue(MSG_TYPE_LOG, line)
            
            self._send_to_queue(MSG_TYPE_STATUS, "Novos dados processados.")

        except error_temp as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro temporário de FTP (RETR): {e}. Tentando reconectar...")
            self._disconnect()
        except error_perm as e:
            self._send_to_queue(MSG_TYPE_ERROR, f"Erro de permissão FTP (RETR) ou arquivo não encontrado: {e}")
            self.current_size = 0 
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
                self._send_to_queue(MSG_TYPE_STATUS, f"Erro ao fechar FTP (pode já estar fechada): {e}")
            finally:
                self.ftp = None

    def _reconnect_with_backoff(self) -> bool:
        """
        Tenta reconectar com backoff exponencial.
        Retorna True se reconectou com sucesso, False caso contrário.
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self._send_to_queue(MSG_TYPE_ERROR, 
                f"Máximo de tentativas de reconexão atingido ({self.max_reconnect_attempts}). Parando monitoramento.")
            return False
        
        # Calcula o delay com backoff exponencial
        delay = min(self.reconnect_delay_base * (2 ** self.reconnect_attempts), 300)  # Máximo de 5 minutos
        self.reconnect_attempts += 1
        
        self._send_to_queue(MSG_TYPE_STATUS, 
            f"Tentativa de reconexão {self.reconnect_attempts}/{self.max_reconnect_attempts} em {delay}s...")
        
        # Aguarda o delay (mas pode ser interrompido pelo stop_event)
        if self._stop_event.wait(delay):
            return False  # Foi solicitado parar
        
        # Tenta reconectar
        self._disconnect()  # Garante que a conexão antiga está fechada
        if self._connect():
            self.reconnect_attempts = 0  # Reseta o contador em caso de sucesso
            return True
        
        return False

    def run(self):
        """O loop principal da thread de monitoramento."""
        self._send_to_queue(MSG_TYPE_STATUS, f"Iniciando monitoramento para: {self.remote_log_path}")
        
        initial_size = self._get_remote_size()
        
        if initial_size == -1:
            self._send_to_queue(MSG_TYPE_ERROR, "Falha ao obter tamanho inicial (verifique o caminho, permissões ou log de erros).")
            # Tenta reconectar com backoff antes de iniciar o loop principal
            if not self._reconnect_with_backoff():
                return  # Falhou ao reconectar, para a thread
            # Tenta obter o tamanho novamente após reconectar
            initial_size = self._get_remote_size()
            if initial_size == -1:
                self._send_to_queue(MSG_TYPE_ERROR, "Falha persistente ao obter tamanho inicial. Parando.")
                return
        
        self.current_size = initial_size
        self._send_to_queue(MSG_TYPE_STATUS, f"Monitoramento iniciado. Tamanho atual: {self.current_size} bytes.")
        self._send_to_queue(MSG_TYPE_LOG, "--- [ Monitoramento iniciado - Aguardando novos dados ] ---")

        while not self._stop_event.is_set():
            try:
                new_size = self._get_remote_size()

                if new_size == -1:
                    # Conexão perdida - tenta reconectar com backoff
                    self._send_to_queue(MSG_TYPE_ERROR, "Conexão perdida. Iniciando reconexão automática...")
                    if not self._reconnect_with_backoff():
                        break  # Falhou ao reconectar, sai do loop
                    continue  # Tenta novamente após reconectar
                
                # Reseta o contador de tentativas em caso de sucesso
                self.reconnect_attempts = 0
                
                if new_size > self.current_size:
                    self._send_to_queue(MSG_TYPE_STATUS, f"Arquivo cresceu. Novo tamanho: {new_size} bytes.")
                    self._fetch_new_data()
                    self.current_size = new_size 
                
                elif new_size < self.current_size:
                    self._send_to_queue(MSG_TYPE_STATUS, "!!! Rotação de log detectada (arquivo diminuiu) !!!")
                    self._send_to_queue(MSG_TYPE_LOG, f"--- [ Rotação de log detectada - Lendo do início (Novo tamanho: {new_size}) ] ---")
                    self.current_size = 0 
                    self._fetch_new_data() 
                    self.current_size = new_size 
                
                # else: new_size == self.current_size (sem mudanças)

            except Exception as e:
                self._send_to_queue(MSG_TYPE_ERROR, f"Erro inesperado no loop: {e}")
                self._disconnect()

            self._stop_event.wait(self.poll_interval)

        self._disconnect()
        self._send_to_queue(MSG_TYPE_STATUS, "Monitoramento parado.")

    def stop(self):
        """Sinaliza para a thread parar."""
        self._send_to_queue(MSG_TYPE_STATUS, "Recebido sinal de parada...")
        self._stop_event.set()