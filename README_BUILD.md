# Instruções de Compilação (Build)

Este documento explica como compilar a aplicação `FTP Utilities` em um executável (`.exe`) e, em seguida, empacotá-lo em um instalador (`setup_*.exe`) usando o script `build.bat`.

## Pré-requisitos

Antes de executar o script, garanta que você tenha:

1.  **Python:** Python 3.7 ou superior instalado e adicionado ao PATH do Windows.
2.  **Inno Setup:** O [Inno Setup (versão 6 ou superior)](https://jrsoftware.org/isinfo.php) deve estar instalado. O script `build.bat` tentará encontrá-lo automaticamente nos caminhos padrão (`C:\Program Files (x86)\Inno Setup 6` ou `C:\Program Files\Inno Setup 6`).
3.  **Arquivos do Projeto:** Todos os arquivos do projeto (`app_tk.py`, `requirements.txt`, `icon.ico`, `instalador.iss`, `FTP_Utilities.spec`, etc.) devem estar na mesma pasta.

## Compilação manual 
1. Execute no terminal pyinstaller --onefile --noconsole --icon=icon.ico --name="FTP_Utilities"  app_tk.py
2. abra o inno setup e execute o arquivo instalador.iss

## Processo de Compilação Automatizado

O script `build.bat` automatiza todo o processo. Para executar:

1.  Navegue até a pasta raiz do projeto.
2.  Dê um duplo clique no arquivo `build.bat`.

### O que o script `build.bat` faz?

O script executará os seguintes passos em ordem:

1.  **Limpeza:** Remove as pastas `dist`, `build` e `.venv` de compilações anteriores para garantir um build limpo.
2.  **Ambiente Virtual:** Cria um ambiente virtual Python na pasta `.venv`.
3.  **Instalação de Dependências:** Ativa o `.venv` e instala todas as bibliotecas listadas no `requirements.txt` (incluindo `pyinstaller`, `watchdog`, e `cryptography`).
4.  **Compilação do EXE (PyInstaller):**
    * Executa o `pyinstaller` usando o arquivo `FTP_Utilities.spec`.
    * Este `.spec` já está configurado para:
        * Usar `app_tk.py` como entrada.
        * Criar um arquivo único (`--onefile`).
        * Ocultar o console (`--noconsole`).
        * **Incluir o ícone (`icon.ico`).**
    * O resultado (`FTP_Utilities.exe`) será salvo na pasta `dist/`.
5.  **Compilação do Instalador (Inno Setup):**
    * Chama o compilador do Inno Setup (`iscc.exe`).
    * Usa o script `instalador.iss` (que foi corrigido para usar caminhos relativos).
    * O Inno Setup pegará o `FTP_Utilities.exe` da pasta `dist/` e o `icon.ico` da raiz do projeto.
    * O instalador final (ex: `setup_ftp_utilities_v1.0.exe`) será salvo em uma nova pasta chamada `Output/`.

## Resultado Final

Após a conclusão do script (que pode levar alguns minutos), você encontrará o instalador final pronto para distribuição na pasta `Output/`.