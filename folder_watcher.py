import os
import time
import threading
from queue import Queue
from ftplib import FTP, error_perm
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Constantes para a fila de status
SYNC_MSG_STATUS = "STATUS"
SYNC_MSG_SUCCESS = "SUCCESS"
SYNC_MSG_ERROR = "ERROR"

class FTPUploadHandler(FileSystemEventHandler):
    """
    Manipulador de eventos do Watchdog que faz o upload de arquivos via FTP
    quando são criados ou modificados.
    """
    
    def __init__(self, job_name: str, config: dict, output_queue: Queue):
        self.job_name = job_name
        self.site_config = config
        self.output_queue = output_queue
        
        self.local_path = config['local_path']
        self.remote_path = config['remote_path']
        
        self.ftp_host = config['ftp_host']
        self.ftp_port = config['ftp_port']
        self.ftp_user = config['ftp_user']
        self.ftp_password = config['ftp_password'] # Senha já descriptografada

    def _log(self, msg_type: str, message: str):
        """Envia uma mensagem formatada para a fila da UI."""
        log_msg = f"[{self.job_name}] {message}"
        try:
            self.output_queue.put_nowait((msg_type, log_msg))
        except Exception as e:
            print(f"Erro na fila de Sync: {e}")

    def _connect_ftp(self) -> FTP | None:
        """Tenta conectar e logar no servidor FTP."""
        try:
            ftp = FTP()
            ftp.connect(self.ftp_host, self.ftp_port, timeout=10)
            ftp.login(self.ftp_user, self.ftp_password)
            ftp.set_pasv(True)
            self._log(SYNC_MSG_STATUS, f"Conectado a {self.ftp_host} para upload...")
            return ftp
        except Exception as e:
            self._log(SYNC_MSG_ERROR, f"Erro ao conectar/logar no FTP: {e}")
            return None

    def _create_remote_dirs(self, ftp: FTP, remote_full_dir: str):
        """Cria recursivamente diretórios no servidor FTP."""
        if not remote_full_dir or remote_full_dir == '/':
            return
        
        parts = remote_full_dir.split('/')
        current_dir = ""
        for part in parts:
            if not part: continue
            
            # Adiciona a barra inicial se o caminho for absoluto
            if not current_dir and remote_full_dir.startswith('/'):
                current_dir = f"/{part}"
            else:
                current_dir = f"{current_dir}/{part}" if current_dir else part
                
            try:
                ftp.cwd(current_dir) # Tenta entrar
            except error_perm:
                try:
                    ftp.mkd(current_dir) # Se falhar, tenta criar
                    self._log(SYNC_MSG_STATUS, f"Diretório remoto '{current_dir}' criado.")
                except error_perm as e_mkd:
                    # Ignora se já existe (concorrência ou erro 521)
                    if "exists" not in str(e_mkd).lower():
                        self._log(SYNC_MSG_ERROR, f"Falha ao criar diretório '{current_dir}': {e_mkd}")
                        raise # Propaga o erro para parar o upload

    def _upload_file(self, local_event_path: str):
        """Thread de trabalho para fazer o upload de um único arquivo."""
        if not os.path.isfile(local_event_path):
            self._log(SYNC_MSG_STATUS, f"Ignorando (não é arquivo): {local_event_path}")
            return

        file_name = os.path.basename(local_event_path)
        
        try:
            # Calcula o caminho relativo (ex: 'subpasta/arquivo.txt')
            relative_path = os.path.relpath(local_event_path, self.local_path)
        except ValueError:
            self._log(SYNC_MSG_ERROR, f"Erro: '{local_event_path}' não está dentro de '{self.local_path}'.")
            return

        # Monta o caminho remoto final
        # os.path.join trata barras / e \
        # .replace garante o formato POSIX (FTP)
        remote_full_path = os.path.join(self.remote_path, relative_path).replace("\\", "/")
        remote_dir = os.path.dirname(remote_full_path)

        self._log(SYNC_MSG_STATUS, f"Iniciando upload de '{file_name}' para '{remote_full_path}'...")
        
        ftp = None
        try:
            ftp = self._connect_ftp()
            if not ftp:
                return # Erro já foi logado

            # 1. Garantir que a estrutura de pastas exista
            self._create_remote_dirs(ftp, remote_dir)
            
            # 2. Fazer o upload
            with open(local_event_path, 'rb') as fp:
                ftp.storbinary(f'STOR {remote_full_path}', fp)
            
            self._log(SYNC_MSG_SUCCESS, f"Upload de '{file_name}' concluído com sucesso.")
            
        except FileNotFoundError:
             self._log(SYNC_MSG_ERROR, f"Arquivo local não encontrado (pode ter sido excluído rapidamente): {local_event_path}")
        except error_perm as e_perm:
             self._log(SYNC_MSG_ERROR, f"Erro de permissão FTP ao enviar '{file_name}': {e_perm}")
        except Exception as e:
             self._log(SYNC_MSG_ERROR, f"Erro inesperado no upload de '{file_name}': {e}")
        finally:
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass # Ignora

    def on_created(self, event):
        if not event.is_directory:
            # Inicia o upload em uma nova thread para não bloquear o watchdog
            threading.Thread(target=self._upload_file, args=(event.src_path,), daemon=True).start()

    def on_modified(self, event):
        if not event.is_directory:
            threading.Thread(target=self._upload_file, args=(event.src_path,), daemon=True).start()

    # on_deleted: Pode ser implementado para excluir arquivos remotos, se desejado.
    # on_moved: Pode ser implementado para renomear/mover remotamente.


class SyncService(threading.Thread):
    """
    Thread principal que gerencia o serviço de observação (Watchdog).
    Ele inicia um Observer e agenda um manipulador para cada 'Sync Job'.
    """
    
    def __init__(self, all_jobs_configs: list, output_queue: Queue):
        super().__init__(daemon=True)
        self.all_jobs_configs = all_jobs_configs
        self.output_queue = output_queue
        self.observer = Observer()
        self._stop_event = threading.Event()

    def _log(self, msg_type: str, message: str):
        try:
            self.output_queue.put_nowait((msg_type, message))
        except Exception as e:
            print(f"Erro na fila de Sync (Serviço): {e}")

    def run(self):
        """Inicia o observador e agenda todos os jobs."""
        if not self.all_jobs_configs:
            self._log(SYNC_MSG_ERROR, "Nenhuma tarefa de sincronização configurada.")
            return

        self._log(SYNC_MSG_STATUS, "Iniciando serviço de Sincronização de Pastas...")
        
        jobs_iniciados = 0
        for job_name, config in self.all_jobs_configs.items():
            local_path = config.get('local_path')
            
            if not os.path.isdir(local_path):
                self._log(SYNC_MSG_ERROR, f"[{job_name}] Erro: Pasta local '{local_path}' não existe. Ignorando.")
                continue

            try:
                # Cria um handler para este job específico
                event_handler = FTPUploadHandler(job_name, config, self.output_queue)
                # Agenda o monitoramento (recursive=True monitora subpastas)
                self.observer.schedule(event_handler, local_path, recursive=True)
                self._log(SYNC_MSG_SUCCESS, f"[{job_name}] Monitoramento iniciado para: '{local_path}'")
                jobs_iniciados += 1
            except Exception as e:
                 self._log(SYNC_MSG_ERROR, f"[{job_name}] Erro ao agendar monitoramento: {e}")

        if jobs_iniciados == 0:
            self._log(SYNC_MSG_ERROR, "Nenhuma tarefa de sincronização válida foi iniciada.")
            return
            
        self.observer.start()
        self._log(SYNC_MSG_STATUS, f"Serviço iniciado. {jobs_iniciados} pasta(s) monitorada(s).")
        
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        finally:
            self.observer.stop()
            self.observer.join()
            self._log(SYNC_MSG_STATUS, "Serviço de Sincronização parado.")

    def stop(self):
        """Sinaliza para a thread do observador parar."""
        self._log(SYNC_MSG_STATUS, "Recebido sinal de parada para o serviço de Sincronização...")
        self._stop_event.set()