

# FTP/SSH Log Tailer (Desktop)

[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/yourusername/ftp_log_tailer)

Uma aplicação desktop (Windows, macOS, Linux) construída com Python e Tkinter para monitorar arquivos de log em servidores FTP/SSH e sincronizar pastas locais com servidores remotos.

A aplicação utiliza threads para o monitoramento (polling) do FTP e sincronização de arquivos, garantindo que a interface do usuário não trave. A comunicação entre as threads de rede e a interface principal é feita de forma segura (thread-safe) usando o módulo `queue`.

## 📋 Sumário

- [Funcionalidades](#-funcionalidades)
- [Instalação](#-instalação-desenvolvimento)
- [Execução](#️-execução-desenvolvimento)
- [Como Usar](#-como-usar)
- [Empacotamento](#-empacotamento-deploy)
- [Solução de Problemas](#-solução-de-problemas)
- [Changelog](#-changelog)
- [Contribuição](#-contribuição)
- [Licença](#-licença)
- [Desenvolvedor](#-desenvolvedor)

## 🚀 Funcionalidades

### Interface com Abas
A aplicação agora possui uma interface organizada em abas:

#### 📄 Aba 1: FTP/SSH Log Tailer
* **Gerenciador de Sites:** Salva múltiplas configurações de servidores FTP e SSH (Host, Usuário, Porta, Tipo de Conexão).
* **Suporte FTP e SSH:** Conecta tanto em servidores FTP tradicionais quanto em servidores SSH/SFTP para maior flexibilidade e segurança.
* **Segurança:** As senhas são **criptografadas** no arquivo `config.json` usando a biblioteca `cryptography` (Fernet). Uma `secret.key` é gerada automaticamente no primeiro uso.
* **Monitoramento "Tail":** Monitora um arquivo de log remoto (ex: `debug.log`) e exibe as novas linhas na tela à medida que são adicionadas.
* **Detecção de Rotação:** Detecta automaticamente se o arquivo de log foi truncado ou substituído (rotação de log) e começa a ler do início do novo arquivo.
* **Interface Responsiva:** A interface não trava (`(Not Responding)`) durante as conexões, pois a lógica de rede roda em uma thread separada.
* **Status em Tempo Real:** Uma barra de status informa o estado da conexão (Conectando, Buscando dados, Erros, etc.).

#### 📁 Aba 2: Sincronização de Pastas
* **Monitoramento Local:** Monitora pastas locais em tempo real usando `watchdog` para detectar criação, modificação e exclusão de arquivos.
* **Sincronização Automática:** Envia automaticamente arquivos novos/modificados para destinos FTP ou SSH configurados.
* **Upload em Lote:** Botão "Carregar Todos" permite fazer upload de todos os arquivos existentes na pasta local para o servidor remoto.
* **Filtragem Inteligente:** Ignora automaticamente arquivos e pastas de desenvolvimento (`.git`, `node_modules`, `venv`, `__pycache__`, etc.).
* **Gerenciador de Tarefas:** Crie, edite e exclua tarefas de sincronização com configurações específicas (pasta local, pasta remota, site FTP/SSH).
* **Log de Atividades:** Visualize em tempo real todas as operações de sincronização realizadas.
* **Execução Independente:** Cada tarefa de sincronização é executada em sua própria thread de serviço.

## 🛠️ Instalação (Desenvolvimento)

### Pré-requisitos

* Python 3.7 ou superior (já inclui Tkinter, ftplib, threading, queue).

### Passos

1. **Clonar o Repositório:**
   ```bash
   git clone [URL_DO_SEU_REPOSITORIO]
   cd ftp_log_tailer_tk
   ```

2. **Criar Ambiente Virtual:**
   ```bash
   python -m venv venv
   ```
   * **No Windows:** `.\venv\Scripts\activate`
   * **No Linux/macOS:** `source venv/bin/activate`

3. **Instalar Dependências:**
   ```bash
   pip install -r requirements.txt
   ```
   *Dependências incluídas: `watchdog` para monitoramento de pastas locais, `paramiko` para conexões SSH*

## ▶️ Execução (Desenvolvimento)

Para iniciar a aplicação diretamente pelo Python:

```bash
python app_tk.py
```

## 📋 Como Usar

### Configuração Inicial

Na primeira execução, dois arquivos serão criados na pasta raiz:
* `secret.key`: Arquivo de criptografia de senhas. **NÃO O COMPARTILHE** e adicione-o ao `.gitignore`.
* `config.json`: Armazena configurações de sites e tarefas de sincronização.

### Aba 1: FTP/SSH Log Tailer

1. **Configurar um Site:**
   * Clique em "Gerenciar Sites..."
   * Selecione o tipo de conexão (FTP ou SSH)
   * Preencha os campos (Nome do Site, Host, Porta, Usuário, Senha)
   * Clique em "Salvar"

2. **Iniciar Monitoramento:**
   * Selecione o site no menu suspenso
   * Insira o caminho completo do arquivo de log remoto
   * Clique em "Iniciar"

### Aba 2: Sincronização de Pastas

1. **Criar Tarefa de Sincronização:**
   * Clique em "Gerenciar Tarefas..."
   * Preencha os campos:
     * Nome da Tarefa
     * Pasta Local (para monitorar)
     * Pasta Remota (destino no servidor)
     * Site FTP/SSH (previamente configurado)
   * Clique em "Salvar"

2. **Iniciar Sincronização:**
   * Selecione a tarefa na lista
   * Clique em "Iniciar Sincronização"
   * O monitoramento da pasta local começará automaticamente

3. **Upload em Lote (Opcional):**
   * Selecione uma tarefa na lista
   * Clique em "Carregar Todos" para enviar todos os arquivos existentes
   * Útil para sincronização inicial ou backup completo

4. **Visualizar Atividades:**
   * O log de sincronização mostrará todas as operações em tempo real
   * Status de cada arquivo (enviado, falha, ignorado)
   * Arquivos filtrados são automaticamente ignorados (ex: `.git`, `node_modules`)

### Arquivos e Pastas Ignorados Automaticamente

A aplicação ignora automaticamente os seguintes padrões para evitar sincronizar arquivos desnecessários:

* **Controle de Versão:** `.git`, `.svn`, `.hg`, `.bzr`
* **Ambientes Virtuais Python:** `venv`, `.venv`, `env`, `.env`, `__pycache__`, `.pytest_cache`
* **Node.js:** `node_modules`, `.npm`, `.yarn`
* **IDEs e Editores:** `.vscode`, `.idea`, `.vs`, `*.swp`, `*.swo`, `*~`
* **Build e Distribuição:** `build`, `dist`, `target`, `bin`, `obj`, `.gradle`
* **Logs e Temporários:** `*.log`, `*.tmp`, `.DS_Store`, `Thumbs.db`
* **Configurações:** `.gitignore`, `.dockerignore`, `.eslintrc*`, `.prettierrc*`

## 📦 Empacotamento (Deploy)

Para distribuir como executável único:

1. **Instale o PyInstaller:**
   ```bash
   pip install pyinstaller
   ```

2. **Execute o comando de empacotamento:**
   ```bash
   pyinstaller --onefile --noconsole --name="FTP_Utilities" app_tk.py --icon=icon.ico
   ```

3. **Distribua o executável:**
   * Windows: `dist/FTPLogTailer.exe`
   * macOS: `dist/FTPLogTailer`
   * Linux: `dist/FTPLogTailer`

### Notas de Empacotamento
* No Windows, o executável pode ser detectado como falso positivo por antivírus
* Para macOS, pode ser necessário assinar o aplicativo para evitar problemas com o Gatekeeper
* Inclua os arquivos `config.json` e `secret.key` na distribuição se necessário

## 🔧 Solução de Problemas

### Problemas Comuns

* **Não consigo conectar ao servidor FTP/SSH:**
  * Verifique credenciais e configurações de rede
  * Confirme se o servidor permite conexões externas
  * Verifique firewalls
  * Para SSH: Certifique-se de que o servidor SSH está rodando na porta correta

* **A sincronização não funciona:**
  * Verifique permissões na pasta local
  * Confirme se a pasta remota existe no servidor
  * Verifique se há espaço suficiente no servidor
  * Para SSH: Verifique permissões de escrita no diretório remoto

* **Perdi meu arquivo `secret.key`:**
  * Exclua `config.json` e reconfigure tudo
  * Uma nova chave será gerada automaticamente

* **Arquivos não são sincronizados:**
  * Verifique se a tarefa está ativa
  * Confirme se o monitoramento local está funcionando
  * Verifique o log de sincronização para erros

## 📝 Changelog

### Versão 1.2
**04-11-2023:**

#### ✨ Novas Funcionalidades
- **feat:** Adicionar funcionalidade de upload em lote para FTP/SSH na interface
  - Botão "Carregar Todos" na aba de Sincronização de Pastas
  - Permite upload de todos os arquivos existentes na pasta local
  - Útil para sincronização inicial e backup completo
  - Execução em thread separada para não travar a interface
- **feat:** Filtragem automática de arquivos e pastas de desenvolvimento
  - Ignora automaticamente `.git`, `node_modules`, `venv`, `__pycache__`, etc.
  - Evita sincronizar arquivos desnecessários
  - Melhora performance e reduz transferência de dados
  - Funciona tanto no monitoramento em tempo real quanto no upload em lote

## 🤝 Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou pull requests.

1. Faça um fork do projeto
2. Crie sua branch de feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 👨‍💻 Desenvolvedor

**Dsantos Info**

[Website](https://dsantosinfo.com.br) | [Email](mailto:contato@dsantosinfo.com.br)