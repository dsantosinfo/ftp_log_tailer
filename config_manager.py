import json
import os
from cryptography.fernet import Fernet

CONFIG_FILE = 'config.json'
KEY_FILE = 'secret.key'

class ConfigManager:
    """
    Gerencia as configurações de conexão FTP e Favoritos, salvando-as em config.json
    e criptografando/descriptografando senhas de sites usando uma chave Fernet.
    """

    def __init__(self):
        self.key = self._load_or_generate_key()
        self.fernet = Fernet(self.key)
        self.configs = self._load_configs()

    def _load_or_generate_key(self) -> bytes:
        """Carrega a chave de criptografia ou gera uma nova se não existir."""
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
        """Carrega o arquivo config.json, garantindo que 'sites' e 'favorites' existam."""
        if not os.path.exists(CONFIG_FILE):
            print(f"Arquivo de configuração não encontrado. Criando {CONFIG_FILE}...")
            default_configs = {"sites": {}, "favorites": {}}
            self._save_configs(default_configs)
            return default_configs
        
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Garante que as chaves principais existam
                data.setdefault('sites', {})
                data.setdefault('favorites', {})
                return data
        except json.JSONDecodeError:
            print(f"Erro ao ler {CONFIG_FILE}. O arquivo pode estar corrompido.")
            return {"sites": {}, "favorites": {}} # Retorna backup vazio

    def _save_configs(self, data: dict):
        """Salva o dicionário de configurações no arquivo config.json."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Erro crítico ao salvar configurações em {CONFIG_FILE}: {e}")

    # --- Métodos de Criptografia ---

    def encrypt_password(self, password: str) -> str:
        """Criptografa uma senha em texto plano."""
        return self.fernet.encrypt(password.encode('utf-8')).decode('utf-8')

    def decrypt_password(self, encrypted_password: str) -> str:
        """Descriptografa uma senha."""
        try:
            return self.fernet.decrypt(encrypted_password.encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"Erro ao descriptografar senha (a chave pode ter mudado ou o dado está corrompido): {e}")
            return ""

    # --- Métodos de Sites ---

    def get_sites(self) -> dict:
        """Retorna o dicionário de sites configurados."""
        return self.configs.get('sites', {})

    def get_site_details(self, site_name: str) -> dict:
        """
        Retorna os detalhes de um site específico, já com a senha descriptografada.
        """
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
        """Salva ou atualiza um site, criptografando a senha."""
        if not site_name or not host or not user:
            raise ValueError("Nome do Site, Host e Usuário são obrigatórios.")

        if 'sites' not in self.configs:
            self.configs['sites'] = {}
            
        encrypted_pass = self.encrypt_password(password_plain)
        
        self.configs['sites'][site_name] = {
            'ftp_host': host,
            'ftp_user': user,
            'ftp_password_encrypted': encrypted_pass,
            'ftp_port': port
        }
        self._save_configs(self.configs)
        print(f"Site '{site_name}' salvo com sucesso.")

    def delete_site(self, site_name: str):
        """Remove um site da configuração."""
        if 'sites' in self.configs and site_name in self.configs['sites']:
            del self.configs['sites'][site_name]
            self._save_configs(self.configs)
            print(f"Site '{site_name}' removido com sucesso.")

            # (NOVO) Limpa favoritos associados a este site
            favorites_to_delete = []
            for fav_name, details in self.get_favorites().items():
                if details.get('site_name') == site_name:
                    favorites_to_delete.append(fav_name)
            
            if favorites_to_delete:
                print(f"Limpando {len(favorites_to_delete)} favoritos associados ao site '{site_name}'...")
                for fav_name in favorites_to_delete:
                    self.delete_favorite(fav_name, save=False) # Não salva ainda
                self._save_configs(self.configs) # Salva uma vez no final

        else:
            print(f"Site '{site_name}' não encontrado para remoção.")

    # --- Métodos de Favoritos (NOVOS) ---

    def get_favorites(self) -> dict:
        """Retorna o dicionário de favoritos."""
        return self.configs.get('favorites', {})

    def save_favorite(self, favorite_name: str, site_name: str, remote_path: str):
        """Salva ou atualiza um favorito."""
        if not all([favorite_name, site_name, remote_path]):
            raise ValueError("Nome do Favorito, Nome do Site e Caminho são obrigatórios.")
        
        if site_name not in self.get_sites():
            raise ValueError(f"Site '{site_name}' não encontrado nas configurações.")

        if 'favorites' not in self.configs:
            self.configs['favorites'] = {}
            
        self.configs['favorites'][favorite_name] = {
            'site_name': site_name,
            'remote_path': remote_path
        }
        self._save_configs(self.configs)
        print(f"Favorito '{favorite_name}' salvo com sucesso.")

    def delete_favorite(self, favorite_name: str, save: bool = True):
        """Remove um favorito da configuração."""
        if 'favorites' in self.configs and favorite_name in self.configs['favorites']:
            del self.configs['favorites'][favorite_name]
            if save:
                self._save_configs(self.configs)
            print(f"Favorito '{favorite_name}' removido com sucesso.")
        else:
            print(f"Favorito '{favorite_name}' não encontrado para remoção.")