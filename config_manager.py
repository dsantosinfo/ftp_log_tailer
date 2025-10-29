import json
import os
from cryptography.fernet import Fernet

CONFIG_FILE = 'config.json'
KEY_FILE = 'secret.key'

class ConfigManager:
    """
    Gerencia as configurações de conexão FTP, salvando-as em config.json
    e criptografando/descriptografando senhas usando uma chave Fernet.
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
        """Carrega o arquivo config.json."""
        if not os.path.exists(CONFIG_FILE):
            print(f"Arquivo de configuração não encontrado. Criando {CONFIG_FILE}...")
            self._save_configs({"sites": {}})
            return {"sites": {}}
        
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Erro ao ler {CONFIG_FILE}. O arquivo pode estar corrompido.")
            # Em caso de falha, retorna um backup vazio para não travar a app
            return {"sites": {}}

    def _save_configs(self, data: dict):
        """Salva o dicionário de configurações no arquivo config.json."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Erro crítico ao salvar configurações em {CONFIG_FILE}: {e}")

    def encrypt_password(self, password: str) -> str:
        """Criptografa uma senha em texto plano."""
        return self.fernet.encrypt(password.encode('utf-8')).decode('utf-8')

    def decrypt_password(self, encrypted_password: str) -> str:
        """Descriptografa uma senha."""
        try:
            return self.fernet.decrypt(encrypted_password.encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"Erro ao descriptografar senha (a chave pode ter mudado ou o dado está corrompido): {e}")
            return "" # Retorna vazio em caso de falha

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
        
        # Cria uma cópia para não modificar o objeto em memória
        site_details = site.copy()
        
        # Descriptografa a senha para uso
        site_details['ftp_password'] = self.decrypt_password(site.get('ftp_password_encrypted', ''))
        
        # Garante valores padrão
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
        else:
            print(f"Site '{site_name}' não encontrado para remoção.")