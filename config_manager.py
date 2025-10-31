import json
import os
from cryptography.fernet import Fernet

# (NOVO) Definir o local correto para salvar os dados (pasta do usuário)
# Isso resolve para C:\Users\<Usuario>\AppData\Local\FTP_Utilities
try:
    APP_DATA_DIR = os.path.join(os.getenv('LOCALAPPDATA'), 'FTP_Utilities')
except TypeError:
     # Fallback caso os.getenv('LOCALAPPDATA') retorne None (raro)
     # Salva na pasta 'Documentos' do usuário como alternativa
     APP_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'FTP_Utilities')

# (MODIFICADO) Usar caminhos absolutos para a pasta AppData
CONFIG_FILE = os.path.join(APP_DATA_DIR, 'config.json')
KEY_FILE = os.path.join(APP_DATA_DIR, 'secret.key')

class ConfigManager:
    """
    Gerencia as configurações de:
    1. Sites (conexões FTP)
    2. Favoritos (Log Tailer)
    3. Sync Jobs (Folder Watcher)
    
    Salva tudo em config.json (em AppData) e gerencia a criptografia.
    """

    def __init__(self):
        # (NOVO) Garantir que a pasta de configuração exista
        self._ensure_app_data_dir()
        
        self.key = self._load_or_generate_key()
        self.fernet = Fernet(self.key)
        self.configs = self._load_configs()

    def _ensure_app_data_dir(self):
        """Cria o diretório em AppData/Local se não existir."""
        try:
            os.makedirs(APP_DATA_DIR, exist_ok=True)
        except OSError as e:
            # Se isso falhar, a aplicação não pode continuar.
            print(f"Erro critico: Nao foi possivel criar o diretorio de dados em {APP_DATA_DIR}: {e}")
            # Lança uma exceção que será pega pelo __main__
            raise Exception(f"Nao foi possivel criar o diretorio de dados em {APP_DATA_DIR}. Verifique as permissoes. Erro: {e}")

    def _load_or_generate_key(self) -> bytes:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            try:
                with open(KEY_FILE, 'wb') as f:
                    f.write(key)
                print(f"Nova chave de segurança gerada em: {KEY_FILE}")
                return key
            except IOError as e:
                print(f"ERRO FATAL AO ESCREVER CHAVE: {e}")
                # Isso será pego pelo __main__ e exibido no MessageBox
                raise Exception(f"Nao foi possivel escrever a chave em {KEY_FILE}. Verifique as permissoes. Erro: {e}")


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
        except IOError as e:
            print(f"ERRO FATAL AO LER CONFIG: {e}")
            raise Exception(f"Nao foi possivel ler a config em {CONFIG_FILE}. Erro: {e}")

    def _save_configs(self, data: dict):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Erro crítico ao salvar configurações em {CONFIG_FILE}: {e}")
            # Em uma app real, poderíamos tentar um fallback ou notificar.

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
        # Decrypt password
        site_details['password'] = self.decrypt_password(site.get('password_encrypted', ''))
        
        # Set defaults based on connection type
        connection_type = site.get('connection_type', 'ftp')
        site_details.setdefault('host', '')
        site_details.setdefault('user', '')
        site_details.setdefault('connection_type', connection_type)
        
        if connection_type == 'ftp':
            site_details.setdefault('port', 21)
        elif connection_type == 'ssh':
            site_details.setdefault('port', 22)
        
        # Backward compatibility
        site_details['ftp_host'] = site_details['host']
        site_details['ftp_user'] = site_details['user']
        site_details['ftp_password'] = site_details['password']
        site_details['ftp_port'] = site_details['port']
        
        return site_details

    def save_site(self, site_name: str, host: str, user: str, password_plain: str, port: int, connection_type: str = 'ftp'):
        if not site_name or not host or not user:
            raise ValueError("Nome do Site, Host e Usuário são obrigatórios.")

        self.configs['sites'][site_name] = {
            'host': host,
            'user': user,
            'password_encrypted': self.encrypt_password(password_plain),
            'port': port,
            'connection_type': connection_type
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