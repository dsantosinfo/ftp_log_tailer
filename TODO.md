# Plano de Refatoração do `app_tk.py`

## 📊 Análise Atual

### Estrutura do Arquivo
- **Total de linhas:** ~950 linhas
- **Classes:** 4 classes no mesmo arquivo
  - `ToolTip` (utilitário)
  - `FTPLogTailerApp` (classe principal - ~650 linhas)
  - `SiteManagerWindow` (janela modal)
  - `SyncJobManagerWindow` (janela modal)

### Problemas Identificados

1. **Classe Principal Monolítica** (`FTPLogTailerApp`)
   - Mistura UI, lógica de negócio, controle de threads e upload
   - Difícil manutenção e testabilidade
   - Viola o Princípio da Responsabilidade Única (SRP)

2. **Responsabilidades Mistas**
   - UI do Log Tailer
   - UI do Folder Sync
   - Lógica de upload FTP/SSH
   - Gerenciamento de filas e threads
   - Callbacks e eventos

3. **Classes Acopladas**
   - `SiteManagerWindow` e `SyncJobManagerWindow` poderiam ser módulos separados

---

## 🎯 Estrutura Final Proposta

```
ftp_log_tailer_tk/
├── app_tk.py                    # Ponto de entrada (minimalista)
├── config_manager.py            # (existente)
├── ftp_poller.py                # (existente)
├── ssh_poller.py                # (existente)
├── ftp_browser.py               # (existente)
├── ssh_browser.py               # (existente)
├── folder_watcher.py            # (existente)
│
├── ui/                          # Componentes de UI
│   ├── __init__.py
│   ├── main_window.py           # Classe FTPLogTailerApp (orquestrador)
│   ├── log_tailer_tab.py        # Aba 1: Log Tailer
│   ├── folder_sync_tab.py       # Aba 2: Folder Sync
│   ├── site_manager.py          # Janela SiteManagerWindow
│   ├── sync_job_manager.py      # Janela SyncJobManagerWindow
│   └── widgets.py               # ToolTip e outros widgets reutilizáveis
│
├── services/                    # Lógica de negócio
│   ├── __init__.py
│   ├── upload_service.py        # Lógica de upload (FTP/SSH)
│   └── queue_processor.py       # Processamento de filas
│
└── utils/                       # Utilitários
    ├── __init__.py
    └── resources.py             # resource_path() e helpers
```

---

## 📋 Fases de Implementação

### Fase 1: Preparação da Estrutura
- [x] Criar pasta `utils/`
- [x] Criar pasta `services/`
- [x] Criar pasta `ui/`
- [x] Criar arquivos `__init__.py` em cada pasta

### Fase 2: Extrair Utilitários
- [x] Criar `utils/resources.py` com a função `resource_path()`
- [x] Criar `ui/widgets.py` com a classe `ToolTip`
- [x] Atualizar imports no `app_tk.py`

### Fase 3: Extrair Janelas Modais
- [x] Criar `ui/site_manager.py` com a classe `SiteManagerWindow`
- [x] Criar `ui/sync_job_manager.py` com a classe `SyncJobManagerWindow`
- [x] Atualizar imports no `app_tk.py`

### Fase 4: Extrair Serviços de Upload
- [x] Criar `services/upload_service.py` com:
  - [x] UploadService classe
  - [x] Métodos: `upload_file_ftp()`, `upload_file_ssh()`
  - [x] Métodos: `create_ftp_dirs()`, `create_ssh_dirs()`
  - [x] Método: `bulk_upload_worker()`
- [x] Atualizar `FTPLogTailerApp` para usar o serviço

### Fase 5: Extrair Processador de Filas
- [ ] Criar `services/queue_processor.py` com:
  - `QueueProcessor` classe
  - Lógica de processamento das filas do Tailer e Sync
- [ ] Atualizar `FTPLogTailerApp` para usar o processador

### Fase 6: Extrair Aba Log Tailer
- [ ] Criar `ui/log_tailer_tab.py` com:
  - Classe `LogTailerTab`
  - Criação de widgets da Aba 1
  - Métodos de favoritos (save, delete, load, select)
  - Métodos de log (clear, copy, export, append)
  - Menu de contexto
  - Controles de monitoramento (start, stop)
- [ ] Integrar com `FTPLogTailerApp`

### Fase 7: Extrair Aba Folder Sync
- [ ] Criar `ui/folder_sync_tab.py` com:
  - Classe `FolderSyncTab`
  - Criação de widgets da Aba 2
  - Métodos de sync jobs (add, edit, remove, toggle)
  - Controles de sincronização (start, stop)
  - Barra de progresso de upload
- [ ] Integrar com `FTPLogTailerApp`

### Fase 8: Refatorar Classe Principal
- [ ] Criar `ui/main_window.py` com:
  - Classe `FTPLogTailerApp` como orquestrador
  - Injeção de dependências (tabs, serviços, config_manager)
  - Gerenciamento de janela principal
  - Notebook com as abas
  - Barra de status
- [ ] Atualizar `app_tk.py` para ser apenas ponto de entrada

### Fase 9: Limpeza de Código Legado
- [ ] Remover classes movidas do `app_tk.py`
- [ ] Remover imports não utilizados
- [ ] Verificar e remover código morto
- [ ] Consolidar imports duplicados
- [ ] Remover comentários obsoletos

### Fase 10: Validação e Testes
- [ ] Testar funcionalidade da Aba 1 (Log Tailer)
- [ ] Testar funcionalidade da Aba 2 (Folder Sync)
- [ ] Testar gerenciador de sites
- [ ] Testar gerenciador de tarefas de sync
- [ ] Testar upload em lote (FTP e SSH)
- [ ] Verificar se não há imports circulares
- [ ] Validar empacotamento PyInstaller

---

## 📐 Diagrama de Dependências

```
app_tk.py (entry point)
    └── ui/main_window.py (FTPLogTailerApp)
            ├── ui/log_tailer_tab.py
            │       └── ui/widgets.py
            ├── ui/folder_sync_tab.py
            │       └── services/upload_service.py
            ├── ui/site_manager.py
            ├── ui/sync_job_manager.py
            └── services/queue_processor.py

config_manager.py (compartilhado)
utils/resources.py (compartilhado)
```

---

## ⚠️ Riscos e Considerações

1. **Imports Circulares**: Cuidado com imports entre módulos
2. **Estado Compartilhado**: Usar injeção de dependência para `config_manager`, `queues`
3. **Callbacks**: Manter referências corretas para callbacks entre módulos
4. **PyInstaller**: Atualizar spec file para incluir novos pacotes

---

## 🚀 Benefícios Esperados

- **Manutenibilidade**: Cada arquivo com responsabilidade única
- **Testabilidade**: Testar serviços isoladamente
- **Legibilidade**: Arquivos menores e mais focados
- **Reutilização**: Widgets e serviços reutilizáveis
- **Colaboração**: Facilita trabalho em equipe

---

## 📝 Notas de Implementação

- Manter compatibilidade com Python 3.8+
- Preservar todas as funcionalidades existentes
- Documentar mudanças em cada commit
- Executar testes manuais após cada fase