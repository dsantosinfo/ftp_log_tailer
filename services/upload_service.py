import threading
import os
from queue import Queue

# Importa as constantes de mensagens
from folder_watcher import SYNC_MSG_STATUS, SYNC_MSG_SUCCESS, SYNC_MSG_ERROR, should_ignore_path

class UploadService:
    """
    Serviço responsável por gerenciar uploads de arquivos FTP/SSH.
    """
    
    def __init__(self, config_manager, folder_sync_queue: Queue):
        self.config_manager = config_manager
        self.folder_sync_queue = folder_sync_queue
        self.upload_cancel_flag = False
        self.upload_in_progress = False
    
    def bulk_upload_worker(self, config: dict, root=None):
        """Worker thread para fazer upload de todos os arquivos."""
        job_name = config['job_name']
        local_path = config['local_path']
        connection_type = config.get('connection_type', 'ftp')
        
        try:
            self.folder_sync_queue.put_nowait((SYNC_MSG_STATUS, f"[{job_name}] Iniciando upload de todos os arquivos..."))
            
            # Conta total de arquivos (excluindo os ignorados)
            total_files = 0
            for root_dir, dirs, files in os.walk(local_path):
                # Filtra diretórios ignorados
                dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root_dir, d))]
                # Conta apenas arquivos não ignorados
                for file in files:
                    file_path = os.path.join(root_dir, file)
                    if not should_ignore_path(file_path):
                        total_files += 1
            
            if total_files == 0:
                self.folder_sync_queue.put_nowait((SYNC_MSG_STATUS, f"[{job_name}] Nenhum arquivo encontrado para upload."))
                if root:
                    root.after(0, self._reset_upload_progress)
                return
            
            self.folder_sync_queue.put_nowait((SYNC_MSG_STATUS, f"[{job_name}] Encontrados {total_files} arquivos para upload."))
            
            uploaded_count = 0
            failed_count = 0
            current_count = 0
            
            # Percorre todos os arquivos
            for root_dir, dirs, files in os.walk(local_path):
                # Filtra diretórios ignorados para não entrar neles
                dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root_dir, d))]
                
                for file in files:
                    # Verifica se foi cancelado
                    if self.upload_cancel_flag:
                        self.folder_sync_queue.put_nowait((SYNC_MSG_STATUS, f"[{job_name}] Upload cancelado pelo usuário."))
                        if root:
                            root.after(0, self._reset_upload_progress)
                        return
                    
                    local_file_path = os.path.join(root_dir, file)
                    
                    # Pula arquivos ignorados
                    if should_ignore_path(local_file_path):
                        continue
                    
                    relative_path = os.path.relpath(local_file_path, local_path)
                    current_count += 1
                    
                    # Atualiza a barra de progresso
                    if root:
                        root.after(0, lambda c=current_count, t=total_files, f=file: self._update_upload_progress(c, t, f))
                    
                    # Faz upload do arquivo
                    if self._upload_single_file(config, local_file_path, relative_path):
                        uploaded_count += 1
                    else:
                        failed_count += 1
            
            # Relatório final
            self.folder_sync_queue.put_nowait((
                SYNC_MSG_SUCCESS, 
                f"[{job_name}] Upload concluído! {uploaded_count} arquivos enviados, {failed_count} falharam."
            ))
            
            # Reseta a barra de progresso
            if root:
                root.after(0, self._reset_upload_progress)
            
        except Exception as e:
            self.folder_sync_queue.put_nowait((SYNC_MSG_ERROR, f"[{job_name}] Erro no upload em lote: {e}"))
            if root:
                root.after(0, self._reset_upload_progress)
    
    def _upload_single_file(self, config: dict, local_file_path: str, relative_path: str) -> bool:
        """Faz upload de um único arquivo. Retorna True se bem-sucedido."""
        connection_type = config.get('connection_type', 'ftp')
        job_name = config['job_name']
        
        try:
            if connection_type == 'ssh':
                return self._upload_file_ssh(config, local_file_path, relative_path)
            else:
                return self._upload_file_ftp(config, local_file_path, relative_path)
        except Exception as e:
            self.folder_sync_queue.put_nowait((SYNC_MSG_ERROR, f"[{job_name}] Erro ao enviar {relative_path}: {e}"))
            return False
    
    def _upload_file_ftp(self, config: dict, local_file_path: str, relative_path: str) -> bool:
        """Upload via FTP."""
        job_name = config['job_name']
        remote_path = config['remote_path']
        
        ftp = None
        try:
            # Conecta
            from ftplib import FTP
            ftp = FTP()
            ftp.connect(config['host'], config['port'], timeout=10)
            ftp.login(config['user'], config['password'])
            ftp.set_pasv(True)
            
            # Constrói caminho remoto
            remote_file_path = os.path.join(remote_path, relative_path).replace("\\", "/")
            remote_dir = os.path.dirname(remote_file_path)
            
            # Cria diretórios se necessário
            self._create_ftp_dirs(ftp, remote_dir)
            
            # Upload
            with open(local_file_path, 'rb') as fp:
                ftp.storbinary(f'STOR {remote_file_path}', fp)
            
            file_size = os.path.getsize(local_file_path)
            self.folder_sync_queue.put_nowait((SYNC_MSG_SUCCESS, f"[{job_name}] Enviado via FTP: {relative_path} ({file_size} bytes)"))
            return True
            
        except Exception as e:
            self.folder_sync_queue.put_nowait((SYNC_MSG_ERROR, f"[{job_name}] Erro FTP ao enviar {relative_path}: {e}"))
            return False
        finally:
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass
    
    def _upload_file_ssh(self, config: dict, local_file_path: str, relative_path: str) -> bool:
        """Upload via SSH/SFTP."""
        job_name = config['job_name']
        remote_path = config['remote_path']
        
        ssh = None
        sftp = None
        try:
            # Conecta
            import paramiko
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=config['host'],
                port=config['port'],
                username=config['user'],
                password=config['password'],
                timeout=10
            )
            sftp = ssh.open_sftp()
            
            # Constrói caminho remoto
            remote_file_path = os.path.join(remote_path, relative_path).replace("\\", "/")
            remote_dir = os.path.dirname(remote_file_path)
            
            # Cria diretórios se necessário
            self._create_ssh_dirs(sftp, remote_dir)
            
            # Upload
            sftp.put(local_file_path, remote_file_path)
            
            file_size = os.path.getsize(local_file_path)
            self.folder_sync_queue.put_nowait((SYNC_MSG_SUCCESS, f"[{job_name}] Enviado via SSH: {relative_path} ({file_size} bytes)"))
            return True
            
        except Exception as e:
            self.folder_sync_queue.put_nowait((SYNC_MSG_ERROR, f"[{job_name}] Erro SSH ao enviar {relative_path}: {e}"))
            return False
        finally:
            if sftp:
                try:
                    sftp.close()
                except Exception:
                    pass
            if ssh:
                try:
                    ssh.close()
                except Exception:
                    pass
    
    def _create_ftp_dirs(self, ftp, remote_full_dir: str):
        """Cria recursivamente diretórios no servidor FTP."""
        if not remote_full_dir or remote_full_dir == '/':
            return
        
        from ftplib import error_perm
        parts = remote_full_dir.split('/')
        current_dir = ""
        for part in parts:
            if not part: continue
            
            if not current_dir and remote_full_dir.startswith('/'):
                current_dir = f"/{part}"
            else:
                current_dir = f"{current_dir}/{part}" if current_dir else part
                
            try:
                ftp.cwd(current_dir)
            except error_perm:
                try:
                    ftp.mkd(current_dir)
                except error_perm:
                    pass  # Ignora se já existe
    
    def _create_ssh_dirs(self, sftp, remote_full_dir: str):
        """Cria recursivamente diretórios no servidor SSH."""
        if not remote_full_dir or remote_full_dir == '/':
            return
        
        parts = remote_full_dir.split('/')
        current_dir = ""
        for part in parts:
            if not part: continue
            
            if not current_dir and remote_full_dir.startswith('/'):
                current_dir = f"/{part}"
            else:
                current_dir = f"{current_dir}/{part}" if current_dir else part
                
            try:
                sftp.stat(current_dir)
            except FileNotFoundError:
                try:
                    sftp.mkdir(current_dir)
                except Exception:
                    pass  # Ignora se já existe
