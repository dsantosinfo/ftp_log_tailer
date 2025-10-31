import os
import paramiko
import stat
from queue import Queue

# Constantes para mensagens da fila
SYNC_MSG_STATUS = "STATUS"
SYNC_MSG_SUCCESS = "SUCCESS"
SYNC_MSG_ERROR = "ERROR"

class SSHSyncHandler:
    """
    Classe para lidar com sincronização de arquivos via SSH/SFTP.
    """
    
    def __init__(self, config: dict, output_queue: Queue):
        self.ssh_host = config.get('host')
        self.ssh_user = config.get('user')
        self.ssh_password = config.get('password')
        self.ssh_port = config.get('port', 22)
        self.remote_path = config.get('remote_path')
        self.output_queue = output_queue
        
        self.ssh = None
        self.sftp = None

    def _send_to_queue(self, msg_type: str, message: str):
        """Envia dados para a fila de forma padronizada."""
        try:
            self.output_queue.put_nowait((msg_type, message))
        except Exception as e:
            print(f"Erro ao enviar para a fila: {e}")

    def connect(self) -> bool:
        """Estabelece conexão SSH."""
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
            return True
        except Exception as e:
            self._send_to_queue(SYNC_MSG_ERROR, f"Falha na conexão SSH: {e}")
            return False

    def disconnect(self):
        """Fecha conexão SSH."""
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
            except Exception:
                pass
            finally:
                self.ssh = None

    def _ensure_remote_directory(self, remote_dir: str):
        """Garante que o diretório remoto existe."""
        try:
            self.sftp.stat(remote_dir)
        except FileNotFoundError:
            # Diretório não existe, criar recursivamente
            parent_dir = os.path.dirname(remote_dir)
            if parent_dir and parent_dir != remote_dir:
                self._ensure_remote_directory(parent_dir)
            self.sftp.mkdir(remote_dir)

    def upload_file(self, local_file_path: str, relative_path: str) -> bool:
        """
        Faz upload de um arquivo para o servidor SSH.
        
        Args:
            local_file_path: Caminho completo do arquivo local
            relative_path: Caminho relativo do arquivo (usado para construir o caminho remoto)
        
        Returns:
            bool: True se o upload foi bem-sucedido, False caso contrário
        """
        if not self.sftp:
            if not self.connect():
                return False

        try:
            # Constrói o caminho remoto
            remote_file_path = os.path.join(self.remote_path, relative_path).replace("\\", "/")
            remote_dir = os.path.dirname(remote_file_path)
            
            # Garante que o diretório remoto existe
            if remote_dir:
                self._ensure_remote_directory(remote_dir)
            
            # Faz o upload
            self.sftp.put(local_file_path, remote_file_path)
            
            file_size = os.path.getsize(local_file_path)
            self._send_to_queue(SYNC_MSG_SUCCESS, f"Enviado via SSH: {relative_path} ({file_size} bytes)")
            return True
            
        except Exception as e:
            self._send_to_queue(SYNC_MSG_ERROR, f"Erro ao enviar {relative_path} via SSH: {e}")
            return False

    def delete_file(self, relative_path: str) -> bool:
        """
        Remove um arquivo do servidor SSH.
        
        Args:
            relative_path: Caminho relativo do arquivo
        
        Returns:
            bool: True se a remoção foi bem-sucedida, False caso contrário
        """
        if not self.sftp:
            if not self.connect():
                return False

        try:
            remote_file_path = os.path.join(self.remote_path, relative_path).replace("\\", "/")
            self.sftp.remove(remote_file_path)
            self._send_to_queue(SYNC_MSG_SUCCESS, f"Removido via SSH: {relative_path}")
            return True
            
        except Exception as e:
            self._send_to_queue(SYNC_MSG_ERROR, f"Erro ao remover {relative_path} via SSH: {e}")
            return False