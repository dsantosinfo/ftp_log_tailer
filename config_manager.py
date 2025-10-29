import json
import os
from cryptography.fernet import Fernet

CONFIG_FILE = 'config.json'
KEY_FILE = 'secret.key'

class ConfigManager:
    """
    Gerencia as configurações de:
    1. Sites (conexões FTP)
    2. Favoritos (Log Tailer)
    3. Sync Jobs (Folder Watcher)
    
    Salva tudo em config.json e gerencia a criptografia.
    """

    def __init__(self):
        self.key = self._load_or_generate_key()
        self.fernet = Fernet(self.key)
        self.configs = self._load_configs()

    def _load_or_generate_key(self) -> bytes:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(KEY_FILE, 'wb') as f:
                f.write(key)
            print(f"Nova chave de segurança gerada: {KEY_FILE}")
            return key

    def _load_configs(self) -> dict:
        """Carrega o config.json, garantindo que as chaves principais existam."""
        if not os.path.exists(CONFIG_FILE):
            print(f"Arquivo de configuração não encontrado. Criando {CONFIG_FILE}...")
            default_configs = {"sites": {}, "favorites": {}, "sync_jobs": {}} # Adicionado sync_jobs
            self._save_configs(default_configs)
            return default_configs
        
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data.setdefault('sites', {})
                data.setdefault('favorites', {})
                data.setdefault('sync_jobs', {}) # Garante que exista
                return data
        except json.JSONDecodeError:
            print(f"Erro ao ler {CONFIG_FILE}. O arquivo pode estar corrompido.")
            return {"sites": {}, "favorites": {}, "sync_jobs": {}} # Backup vazio

    def _save_configs(self, data: dict):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Erro crítico ao salvar configurações em {CONFIG_FILE}: {e}")

    # --- Criptografia ---

    def encrypt_password(self, password: str) -> str:
        return self.fernet.encrypt(password.encode('utf-8')).decode('utf-8')

    def decrypt_password(self, encrypted_password: str) -> str:
        try:
            return self.fernet.decrypt(encrypted_password.encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"Erro ao descriptografar senha: {e}")
            return ""

    # --- Sites ---

    def get_sites(self) -> dict:
        return self.configs.get('sites', {})

    def get_site_details(self, site_name: str) -> dict:
        site = self.get_sites().get(site_name)
        if not site:
            return {}
        
        site_details = site.copy()
        site_details['ftp_password'] = self.decrypt_password(site.get('ftp_password_encrypted', ''))
        site_details.setdefault('ftp_host', '')
        site_details.setdefault('ftp_user', '')
        site_details.setdefault('ftp_port', 21)
        
        return site_details

    def save_site(self, site_name: str, host: str, user: str, password_plain: str, port: int):
        if not site_name or not host or not user:
            raise ValueError("Nome do Site, Host e Usuário são obrigatórios.")

        self.configs['sites'][site_name] = {
            'ftp_host': host,
            'ftp_user': user,
            'ftp_password_encrypted': self.encrypt_password(password_plain),
            'ftp_port': port
        }
        self._save_configs(self.configs)

    def delete_site(self, site_name: str):
        if 'sites' in self.configs and site_name in self.configs['sites']:
            del self.configs['sites'][site_name]
            
            # Limpa favoritos e sync_jobs associados
            self._cleanup_on_site_delete(site_name)
            
            self._save_configs(self.configs)
            print(f"Site '{site_name}' removido com sucesso.")

    def _cleanup_on_site_delete(self, site_name: str):
        """Limpa entradas em 'favorites' e 'sync_jobs' que referenciavam o site excluído."""
        favs_to_del = [name for name, d in self.get_favorites().items() if d.get('site_name') == site_name]
        for name in favs_to_del:
            del self.configs['favorites'][name]
            print(f"Favorito '{name}' removido (site órfão).")

        jobs_to_del = [name for name, d in self.get_sync_jobs().items() if d.get('site_name') == site_name]
        for name in jobs_to_del:
            del self.configs['sync_jobs'][name]
            print(f"Sync Job '{name}' removido (site órfão).")

    # --- Favoritos (Log Tailer) ---

    def get_favorites(self) -> dict:
        return self.configs.get('favorites', {})

    def save_favorite(self, favorite_name: str, site_name: str, remote_path: str):
        if not all([favorite_name, site_name, remote_path]):
            raise ValueError("Nome do Favorito, Nome do Site e Caminho são obrigatórios.")
        if site_name not in self.get_sites():
            raise ValueError(f"Site '{site_name}' não encontrado.")

        self.configs['favorites'][favorite_name] = {
            'site_name': site_name,
            'remote_path': remote_path
        }
        self._save_configs(self.configs)

    def delete_favorite(self, favorite_name: str, save: bool = True):
        if 'favorites' in self.configs and favorite_name in self.configs['favorites']:
            del self.configs['favorites'][favorite_name]
            if save:
                self._save_configs(self.configs)

    # --- Sync Jobs (Folder Watcher) (NOVO) ---

    def get_sync_jobs(self) -> dict:
        """Retorna o dicionário de tarefas de sincronização."""
        return self.configs.get('sync_jobs', {})

    def save_sync_job(self, job_name: str, site_name: str, local_path: str, remote_path: str):
        """Salva ou atualiza uma tarefa de sincronização."""
        if not all([job_name, site_name, local_path, remote_path]):
            raise ValueError("Todos os campos (Nome, Site, Local, Remoto) são obrigatórios.")
        if site_name not in self.get_sites():
            raise ValueError(f"Site '{site_name}' não encontrado nas configurações.")
        
        self.configs['sync_jobs'][job_name] = {
            'site_name': site_name,
            'local_path': local_path,
            'remote_path': remote_path
        }
        self._save_configs(self.configs)

    def delete_sync_job(self, job_name: str, save: bool = True):
        """Remove uma tarefa de sincronização."""
        if 'sync_jobs' in self.configs and job_name in self.configs['sync_jobs']:
            del self.configs['sync_jobs'][job_name]
            if save:
                self._save_configs(self.configs)