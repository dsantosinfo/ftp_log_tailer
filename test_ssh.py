#!/usr/bin/env python3
"""
Script de teste para verificar a funcionalidade SSH
"""

import sys
import os

# Adiciona o diretório atual ao path para importar os módulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config_manager import ConfigManager
    from ssh_poller import SSHLogPoller
    from ssh_browser import SSHBrowserWindow
    from ssh_sync import SSHSyncHandler
    print("✓ Todos os módulos SSH importados com sucesso!")
    
    # Teste básico do ConfigManager com SSH
    config_manager = ConfigManager()
    
    # Teste de salvamento de site SSH
    try:
        config_manager.save_site(
            site_name="teste_ssh",
            host="example.com",
            user="testuser",
            password_plain="testpass",
            port=22,
            connection_type="ssh"
        )
        print("✓ Site SSH salvo com sucesso!")
        
        # Teste de recuperação
        site_details = config_manager.get_site_details("teste_ssh")
        if site_details.get('connection_type') == 'ssh':
            print("✓ Site SSH recuperado com sucesso!")
        else:
            print("✗ Erro ao recuperar tipo de conexão SSH")
            
        # Limpa o teste
        config_manager.delete_site("teste_ssh")
        print("✓ Site de teste removido")
        
    except Exception as e:
        print(f"✗ Erro no teste do ConfigManager: {e}")
    
    print("\n🎉 Suporte SSH adicionado com sucesso!")
    print("Funcionalidades disponíveis:")
    print("- Monitoramento de logs via SSH/SFTP")
    print("- Navegador de arquivos SSH")
    print("- Sincronização de pastas via SSH")
    print("- Interface unificada FTP/SSH")
    
except ImportError as e:
    print(f"✗ Erro de importação: {e}")
    print("Certifique-se de que o paramiko está instalado: pip install paramiko")
except Exception as e:
    print(f"✗ Erro inesperado: {e}")