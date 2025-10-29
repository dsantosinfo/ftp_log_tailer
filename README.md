

# FTP Log Tailer (Desktop)

[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/yourusername/ftp_log_tailer)

Uma aplicação desktop (Windows, macOS, Linux) construída com Python e Tkinter para monitorar arquivos de log em servidores FTP em tempo real, similar ao comando `tail -f`.

A aplicação utiliza threads para o monitoramento (polling) do FTP, garantindo que a interface do usuário não trave. A comunicação entre a thread de rede e a interface principal é feita de forma segura (thread-safe) usando o módulo `queue`.

## 📋 Sumário

- [Funcionalidades](#-funcionalidades)
- [Instalação](#-instalação-desenvolvimento)
- [Execução](#️-execução-desenvolvimento)
- [Como Usar](#-como-usar)
- [Empacotamento](#-empacotamento-deploy)
- [Solução de Problemas](#-solução-de-problemas)
- [Contribuição](#-contribuição)
- [Licença](#-licença)
- [Desenvolvedor](#-desenvolvedor)

## 🚀 Funcionalidades

* **Gerenciador de Sites:** Salva múltiplas configurações de servidores FTP (Host, Usuário, Porta).
* **Segurança:** As senhas de FTP são **criptografadas** no arquivo `config.json` usando a biblioteca `cryptography` (Fernet). Uma `secret.key` é gerada automaticamente no primeiro uso.
* **Monitoramento "Tail":** Monitora um arquivo de log remoto (ex: `debug.log`) e exibe as novas linhas na tela à medida que são adicionadas.
* **Detecção de Rotação:** Detecta automaticamente se o arquivo de log foi truncado ou substituído (rotação de log) e começa a ler do início do novo arquivo.
* **Interface Responsiva:** A interface não trava (`(Not Responding)`) durante as conexões FTP, pois a lógica de rede roda em uma thread separada.
* **Status em Tempo Real:** Uma barra de status informa o estado da conexão (Conectando, Buscando dados, Erros, etc.).

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

## ▶️ Execução (Desenvolvimento)

Para iniciar a aplicação diretamente pelo Python:

```bash
python app_tk.py
```

## 📋 Como Usar

### a. Primeiro Uso (Geração da Chave)

Na primeira vez que você executar a aplicação (`python app_tk.py`), dois arquivos serão criados na pasta raiz:

* `secret.key`: (MUITO IMPORTANTE) Este arquivo criptografa suas senhas. **NÃO O COMPARTILHE** e adicione-o ao `.gitignore`. Se você perdê-lo, todas as senhas salvas em `config.json` se tornarão ilegíveis.
* `config.json`: Armazena as configurações dos seus sites.

### b. Configurar um Site

1. Com a aplicação aberta, clique no botão "Gerenciar Sites...".
2. Na nova janela, preencha os campos (Nome do Site, Host, Porta, Usuário, Senha).
3. Clique em "Salvar".
4. Feche a janela de gerenciamento. O Combobox na tela principal será atualizado.

### c. Iniciar o Monitoramento

1. Selecione o site desejado no menu suspenso "Site".
2. Insira o caminho completo do arquivo de log no campo "Caminho do Log" (ex: `/public_html/wp-content/debug.log`).
3. Clique em "Iniciar".
4. A tela de log começará a ser preenchida. Novas linhas aparecerão automaticamente.

## 📦 Empacotamento (Deploy)

Para distribuir esta aplicação como um executável único (.exe no Windows ou um app no macOS) que não exige que o usuário tenha o Python instalado, você pode usar o PyInstaller.

### Pré-requisitos

Certifique-se de que o PyInstaller está instalado no seu ambiente virtual:

```bash
pip install pyinstaller
```

### Comando de Empacotamento

Execute o comando a seguir para criar o executável (substitua `app_tk.py` se necessário):

```bash
# Comando para criar um executável único (one-file) e sem janela de console
pyinstaller --onefile --noconsole --name="FTPLogTailer" app_tk.py
```

* `--onefile`: Agrupa tudo em um único arquivo.
* `--noconsole` (ou `-w`): Impede que o terminal/console apareça ao executar a aplicação (essencial para apps de UI).
* `--name`: Define o nome do executável final.

O executável final estará na pasta `dist/`. Você pode distribuir o arquivo `FTPLogTailer` (ou `FTPLogTailer.exe`) para seus usuários.

### Notas de Empacotamento

* No Windows, o executável pode ser detectado por alguns antivírus como falso positivo. Isso é comum com aplicações empacotadas com PyInstaller.
* Para macOS, você pode precisar assinar o aplicativo para evitar problemas de segurança do Gatekeeper.
* Para Linux, geralmente não são necessários passos adicionais.

## 🔧 Solução de Problemas

### Problemas Comuns

* **Não consigo conectar ao servidor FTP:**
  * Verifique se as credenciais estão corretas
  * Confirme se o servidor FTP permite conexões externas
  * Verifique se há firewalls bloqueando a conexão

* **A aplicação trava ao iniciar:**
  * Certifique-se de que o arquivo `secret.key` existe no mesmo diretório da aplicação
  * Verifique se as permissões de arquivo estão corretas

* **Perdi meu arquivo `secret.key`:**
  * Infelizmente, você precisará excluir o arquivo `config.json` e reconfigurar todos os seus sites
  * Uma nova chave será gerada automaticamente na próxima execução

## 🤝 Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir uma issue para reportar bugs ou sugerir melhorias. Pull requests também são encorajados.

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