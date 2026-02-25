import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, scrolledtext, font, filedialog
import queue
import threading
import os
import sys
from ftplib import FTP

from config_manager import ConfigManager
from ftp_poller import FTPLogPoller, MSG_TYPE_LOG, MSG_TYPE_STATUS, MSG_TYPE_ERROR
from ssh_poller import SSHLogPoller
from ftp_browser import FTPBrowserWindow
from ssh_browser import SSHBrowserWindow
from folder_watcher import SyncService, SYNC_MSG_STATUS, SYNC_MSG_SUCCESS, SYNC_MSG_ERROR, should_ignore_path

from utils.resources import resource_path
from ui.widgets import ToolTip
from ui.site_manager import SiteManagerWindow
from ui.sync_job_manager import SyncJobManagerWindow
from services.upload_service import UploadService

class FTPLogTailerApp:
    
    def __init__(self, root):
        self.root = root
        self.root.title("Dsantos Info - FTP Utilities (Tailer & Sync)")
        self.root.geometry("1000x750")

        # --- (NOVO) Adicionar Ícone da Janela ---
        try:
            # Usamos a função resource_path para garantir que o .exe encontre o ícone
            icon_path = resource_path("icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            # Se falhar (ex: icon.ico não encontrado), apenas loga no console
            print(f"Aviso: Nao foi possivel carregar o icone da janela: {e}")
        # --- Fim da Adição ---

        self.config_manager = ConfigManager()
        self.log_tailer_queue = queue.Queue()
        self.folder_sync_queue = queue.Queue()  
        self.poller_thread = None  
        self.sync_service_thread = None
        
        # --- (NOVO) Controle de Upload ---
        self.upload_cancel_flag = False
        self.upload_in_progress = False
        
        # --- (NOVO) Serviço de Upload ---
        self.upload_service = UploadService(self.config_manager, self.folder_sync_queue)
        
        self._setup_styles()
        self._create_main_widgets()
        
        self._load_sites_to_combobox()
        self._load_favorites_to_combobox()
        self._load_sync_jobs_to_treeview()  
        
        self._start_queues_checker()  
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')  
        self.log_font = font.Font(family="Consolas", size=10)
        self.style.configure("SyncLog.TText", background="#2b2b2b", foreground="#cccccc", font=self.log_font, wrap="word")
        self.style.map("SyncLog.TText", background=[('disabled', '#2b2b2b')], foreground=[('disabled', '#cccccc')])

    def _create_main_widgets(self):
        self.notebook = ttk.Notebook(self.root, padding="5")
        
        # --- Aba 1: Log Tailer ---
        self.tab1_frame = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(self.tab1_frame, text=" FTP Log Tailer (Real-time) ")
        self._create_log_tailer_tab(self.tab1_frame)  
        
        # --- Aba 2: Folder Sync ---
        self.tab2_frame = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(self.tab2_frame, text=" Sincronização de Pastas (Watcher) ")
        self._create_folder_sync_tab(self.tab2_frame)  
        
        self.notebook.pack(fill='both', expand=True)

        self.status_bar = ttk.Label(self.root, text="Pronto.", padding="5", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill='x', side=tk.BOTTOM)

    # --- Início: Aba 1 (Log Tailer) ---

    def _create_log_tailer_tab(self, parent_frame: ttk.Frame):
        config_frame = ttk.Frame(parent_frame)
        config_frame.pack(fill='x')
        
        fav_frame = ttk.Frame(config_frame)
        fav_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(fav_frame, text="Favoritos:").pack(side=tk.LEFT, padx=(0, 5))
        self.fav_combo = ttk.Combobox(fav_frame, state="readonly", width=40)
        self.fav_combo.pack(side=tk.LEFT, padx=5, fill='x', expand=True)
        self.fav_combo.bind("<<ComboboxSelected>>", self._on_favorite_selected)
        self.fav_save_btn = ttk.Button(fav_frame, text="Salvar Favorito...", command=self._save_favorite)
        self.fav_save_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.fav_save_btn, "Salvar caminho atual como favorito")
        self.fav_del_btn = ttk.Button(fav_frame, text="Excluir Favorito", command=self._delete_favorite, state=tk.DISABLED)
        self.fav_del_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.fav_del_btn, "Excluir favorito selecionado")

        control_frame = ttk.Frame(config_frame)
        control_frame.pack(fill='x')
        ttk.Label(control_frame, text="Site:").pack(side=tk.LEFT, padx=(0, 5))
        self.site_combo = ttk.Combobox(control_frame, state="readonly", width=30)
        self.site_combo.pack(side=tk.LEFT, padx=5)
        self.site_combo.bind("<<ComboboxSelected>>", self._on_site_selected)
        self.manage_sites_btn = ttk.Button(control_frame, text="Gerenciar Sites...", command=self._open_site_manager)
        self.manage_sites_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.manage_sites_btn, "Abrir gerenciador de sites FTP/SSH")
        self.start_btn = ttk.Button(control_frame, text="Iniciar", command=self._start_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=(20, 5))
        ToolTip(self.start_btn, "Iniciar monitoramento do log")
        self.stop_btn = ttk.Button(control_frame, text="Parar", command=self._stop_monitoring, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.stop_btn, "Parar monitoramento")
        
        path_frame = ttk.Frame(config_frame, padding=(0, 10, 0, 0))
        path_frame.pack(fill='x')
        ttk.Label(path_frame, text="Caminho do Log:").pack(side=tk.LEFT, padx=(0, 5))
        self.log_path_entry = ttk.Entry(path_frame)
        self.log_path_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 5))
        self.log_path_entry.insert(0, "/public_html/wp-content/debug.log")  
        self.log_path_entry.bind("<KeyRelease>", self._on_path_entry_change)
        self.browse_btn = ttk.Button(path_frame, text="Procurar...", command=self._open_ftp_browser, state=tk.DISABLED)
        self.browse_btn.pack(side=tk.LEFT)

        log_btn_frame = ttk.Frame(parent_frame, padding=(0, 5, 0, 5))
        log_btn_frame.pack(fill='x')
        self.clear_log_btn = ttk.Button(log_btn_frame, text="Limpar Log", command=self._clear_log)
        self.clear_log_btn.pack(side=tk.LEFT)
        self.copy_log_btn = ttk.Button(log_btn_frame, text="Copiar Log", command=self._copy_log)
        self.copy_log_btn.pack(side=tk.LEFT, padx=10)
        self.export_log_btn = ttk.Button(log_btn_frame, text="Exportar Log...", command=self._export_log)
        self.export_log_btn.pack(side=tk.LEFT)

        self.log_display_tailer = scrolledtext.ScrolledText(parent_frame, state=tk.DISABLED)
        self.log_display_tailer.configure(font=self.log_font, bg="#2b2b2b", fg="#cccccc", wrap=tk.WORD, insertbackground="#ffffff")
        self.log_display_tailer.tag_configure("STATUS", foreground="#808080")  
        self.log_display_tailer.tag_configure("ERROR", foreground="#ff6347")    
        self.log_display_tailer.tag_configure("LOG", foreground="#cccccc")     
        self.log_display_tailer.tag_configure("HIGHLIGHT", background="#4a4a4a")
        self.log_display_tailer.pack(fill='both', expand=True, pady=(0, 5))
        # Menu de contexto
        self.log_display_tailer.bind("<Button-3>", self._show_tailer_context_menu)
        self._create_tailer_context_menu()

    # --- Início: Aba 2 (Folder Sync) ---

    def _create_folder_sync_tab(self, parent_frame: ttk.Frame):
        sync_control_frame = ttk.Frame(parent_frame, padding=(0, 5))
        sync_control_frame.pack(fill='x')
        self.sync_start_btn = ttk.Button(sync_control_frame, text="Iniciar Sincronização", command=self._start_sync_service)
        self.sync_start_btn.pack(side=tk.LEFT)
        ToolTip(self.sync_start_btn, "Iniciar monitoramento de pastas")
        self.sync_stop_btn = ttk.Button(sync_control_frame, text="Parar Sincronização", command=self._stop_sync_service, state=tk.DISABLED)
        self.sync_stop_btn.pack(side=tk.LEFT, padx=10)
        ToolTip(self.sync_stop_btn, "Parar monitoramento")

        sync_main_frame = ttk.Frame(parent_frame, padding=(0, 10))
        sync_main_frame.pack(fill='both', expand=True)
        
        jobs_frame = ttk.Labelframe(sync_main_frame, text="Pastas Monitoradas", padding="5")
        jobs_frame.pack(side=tk.LEFT, fill='y', padx=(0, 10))

        # --- (NOVO) TreeView com scrollbars horizontal e vertical ---
        tree_container = ttk.Frame(jobs_frame)
        tree_container.pack(fill='both', expand=True)
        
        # Scrollbar vertical
        tree_v_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL)
        tree_v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Scrollbar horizontal
        tree_h_scroll = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL)
        tree_h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        # TreeView com coluna de Status (ativo/inativo)
        self.sync_jobs_tree = ttk.Treeview(
            tree_container, 
            columns=("Status", "Site", "Local", "Remoto"), 
            selectmode="browse", 
            height=10,
            yscrollcommand=tree_v_scroll.set,
            xscrollcommand=tree_h_scroll.set
        )
        self.sync_jobs_tree.heading("#0", text="Nome Tarefa")
        self.sync_jobs_tree.heading("Status", text="Status")
        self.sync_jobs_tree.heading("Site", text="Site FTP")
        self.sync_jobs_tree.heading("Local", text="Pasta Local")
        self.sync_jobs_tree.heading("Remoto", text="Pasta Remota")
        
        # Configuração das colunas com stretch habilitado
        self.sync_jobs_tree.column("#0", width=150, minwidth=100, stretch=False)
        self.sync_jobs_tree.column("Status", width=70, minwidth=60, stretch=False, anchor="center")
        self.sync_jobs_tree.column("Site", width=100, minwidth=80, stretch=False)
        self.sync_jobs_tree.column("Local", width=250, minwidth=150, stretch=True)
        self.sync_jobs_tree.column("Remoto", width=250, minwidth=150, stretch=True)
        
        self.sync_jobs_tree.pack(side=tk.LEFT, fill='both', expand=True)
        
        # Configura scrollbars
        tree_v_scroll.config(command=self.sync_jobs_tree.yview)
        tree_h_scroll.config(command=self.sync_jobs_tree.xview)
        
        self.sync_jobs_tree.bind("<<TreeviewSelect>>", self._on_sync_job_select)

        jobs_btn_frame = ttk.Frame(jobs_frame)
        jobs_btn_frame.pack(fill='x', pady=5)
        self.sync_add_btn = ttk.Button(jobs_btn_frame, text="Adicionar...", command=self._add_sync_job)
        self.sync_add_btn.pack(side=tk.LEFT)
        ToolTip(self.sync_add_btn, "Adicionar nova tarefa de sincronização")
        self.sync_edit_btn = ttk.Button(jobs_btn_frame, text="Editar", command=self._edit_sync_job, state=tk.DISABLED)
        self.sync_edit_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.sync_edit_btn, "Editar tarefa selecionada")
        self.sync_del_btn = ttk.Button(jobs_btn_frame, text="Remover", command=self._remove_sync_job, state=tk.DISABLED)
        self.sync_del_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.sync_del_btn, "Excluir tarefa selecionada")
        self.sync_toggle_btn = ttk.Button(jobs_btn_frame, text="Desativar", command=self._toggle_sync_job, state=tk.DISABLED)
        self.sync_toggle_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.sync_toggle_btn, "Ativar/Desativar tarefa")
        self.upload_all_btn = ttk.Button(jobs_btn_frame, text="Carregar Todos", command=self._upload_all_files, state=tk.DISABLED)
        self.upload_all_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(self.upload_all_btn, "Fazer upload de todos os arquivos")
        
        # --- (NOVO) Barra de Progresso de Upload ---
        progress_frame = ttk.Frame(jobs_frame)
        progress_frame.pack(fill='x', pady=5)
        self.upload_progress_var = tk.DoubleVar(value=0)
        self.upload_progressbar = ttk.Progressbar(progress_frame, variable=self.upload_progress_var, maximum=100, length=200)
        self.upload_progressbar.pack(side=tk.LEFT, padx=5)
        self.upload_progress_label = ttk.Label(progress_frame, text="")
        self.upload_progress_label.pack(side=tk.LEFT, padx=5)
        self.upload_cancel_btn = ttk.Button(progress_frame, text="Cancelar", command=self._cancel_upload, state=tk.DISABLED)
        self.upload_cancel_btn.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.Labelframe(sync_main_frame, text="Log de Sincronização", padding="5")
        log_frame.pack(fill='both', expand=True)

        # --- (NOVO) Frame de botões do log de sincronização ---
        sync_log_btn_frame = ttk.Frame(log_frame)
        sync_log_btn_frame.pack(fill='x', pady=(0, 5))
        self.clear_sync_log_btn = ttk.Button(sync_log_btn_frame, text="Limpar Log", command=self._clear_sync_log)
        self.clear_sync_log_btn.pack(side=tk.LEFT)
        
        self.log_display_sync = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED)
        self.log_display_sync.configure(font=self.log_font, bg="#2b2b2b", fg="#cccccc", wrap=tk.WORD, insertbackground="#ffffff")
        self.log_display_sync.tag_configure(SYNC_MSG_STATUS, foreground="#808080")  
        self.log_display_sync.tag_configure(SYNC_MSG_ERROR, foreground="#ff6347")    
        self.log_display_sync.tag_configure(SYNC_MSG_SUCCESS, foreground="#76c7c0")  
        self.log_display_sync.pack(fill='both', expand=True)
    
    # --- Lógica de Filas e Threads (Unificado) ---
    
    def _start_queues_checker(self):
        self.root.after(100, self._process_queues)

    def _process_queues(self):
        # 1. Processa Fila do Log Tailer (Aba 1)
        try:
            while True:  
                msg_type, message = self.log_tailer_queue.get_nowait()
                if msg_type == MSG_TYPE_STATUS:
                    self.status_bar.config(text=message)
                    if "Monitoramento parado" in message:
                        self._set_tailer_ui_state(monitoring=False)
                elif msg_type == MSG_TYPE_ERROR:
                    self._append_log_tailer(message, "ERROR")
                    self.status_bar.config(text=f"Erro (Tailer): {message}")
                elif msg_type == MSG_TYPE_LOG:
                    self._append_log_tailer(message, "LOG")
        except queue.Empty:
            pass  
        except Exception as e:
            print(f"Erro ao processar fila do Tailer: {e}")

        # 2. Processa Fila do Folder Sync (Aba 2)
        try:
            while True:
                msg_type, message = self.folder_sync_queue.get_nowait()
                self._append_log_sync(message, msg_type)  
                if "Serviço de Sincronização parado" in message:
                    self._set_sync_ui_state(monitoring=False)
                elif "Serviço iniciado" in message:
                    self.status_bar.config(text=message)
        except queue.Empty:
            pass  
        except Exception as e:
            print(f"Erro ao processar fila do Sync: {e}")
        
        self.root.after(200, self._process_queues)  

    def _on_closing(self):
        self._stop_monitoring()
        self._stop_sync_service()  
        if self.poller_thread:
            self.poller_thread.join(timeout=1.0)  
        if self.sync_service_thread:
            self.sync_service_thread.join(timeout=1.0)
        self.root.destroy()
        
    # --- Lógica Específica da Aba 1 (Log Tailer) ---

    def _load_sites_to_combobox(self):
        sites = list(self.config_manager.get_sites().keys())
        self.site_combo['values'] = sites
        if sites:
            self.site_combo.current(0)
            self._on_site_selected(None)  
        else:
            self.browse_btn.config(state=tk.DISABLED)

    def _load_favorites_to_combobox(self):
        favorites = list(self.config_manager.get_favorites().keys())
        self.fav_combo['values'] = favorites
        if favorites: self.fav_combo.set("")
        self.fav_del_btn.config(state=tk.DISABLED)

    def _on_site_selected(self, event):
        if self.site_combo.get():
            self.browse_btn.config(state=tk.NORMAL)
        else:
            self.browse_btn.config(state=tk.DISABLED)
        self._clear_favorite_selection()  

    def _on_favorite_selected(self, event):
        fav_name = self.fav_combo.get()
        if not fav_name:
            self.fav_del_btn.config(state=tk.DISABLED)
            return
        fav_details = self.config_manager.get_favorites().get(fav_name)
        if fav_details:
            site_name = fav_details.get('site_name')
            if site_name not in self.config_manager.get_sites():
                messagebox.showerror("Erro de Favorito", f"O site '{site_name}' não existe mais.", parent=self.root)
                self.fav_combo.set("")
                return
            self.site_combo.set(site_name)
            self.log_path_entry.delete(0, tk.END)
            self.log_path_entry.insert(0, fav_details.get('remote_path'))
            self.fav_del_btn.config(state=tk.NORMAL)
            self._on_site_selected(None)  
        else:
            self.fav_del_btn.config(state=tk.DISABLED)

    def _on_path_entry_change(self, event):
        self._clear_favorite_selection()
        
    def _clear_favorite_selection(self):
        if self.fav_combo.get():
            self.fav_combo.set("")
            self.fav_del_btn.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log_display_tailer.configure(state=tk.NORMAL)
        self.log_display_tailer.delete('1.0', tk.END)
        self.log_display_tailer.configure(state=tk.DISABLED)
        self.status_bar.config(text="Log (Tailer) limpo.")

    def _copy_log(self):
        try:
            log_content = self.log_display_tailer.get('1.0', tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(log_content)
            self.status_bar.config(text="Log (Tailer) copiado.")
        except Exception as e:
            self.status_bar.config(text=f"Erro ao copiar: {e}")

    def _export_log(self):
        try:
            log_content = self.log_display_tailer.get('1.0', tk.END)
            if not log_content.strip():
                messagebox.showinfo("Log Vazio", "Não há nada para exportar.", parent=self.root)
                return
            file_path = filedialog.asksaveasfilename(title="Exportar Log Como...", defaultextension=".txt", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f: f.write(log_content)
                self.status_bar.config(text=f"Log (Tailer) exportado.")
        except Exception as e:
            messagebox.showerror("Erro ao Exportar", f"Não foi possível salvar:\n{e}", parent=self.root)

    def _save_favorite(self):
        site_name = self.site_combo.get()
        remote_path = self.log_path_entry.get().strip()
        if not site_name or not remote_path:
            messagebox.showwarning("Dados Incompletos", "Selecione um Site e preencha um Caminho.", parent=self.root)
            return
        fav_name = simpledialog.askstring("Salvar Favorito", "Nome para este favorito:", parent=self.root)
        if fav_name:
            try:
                self.config_manager.save_favorite(fav_name.strip(), site_name, remote_path)
                self._load_favorites_to_combobox()
                self.fav_combo.set(fav_name.strip())  
                self.fav_del_btn.config(state=tk.NORMAL)
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", f"{e}", parent=self.root)

    def _delete_favorite(self):
        fav_name = self.fav_combo.get()
        if not fav_name: return
        if messagebox.askyesno("Confirmar Exclusão", f"Excluir o favorito '{fav_name}'?", parent=self.root):
            try:
                self.config_manager.delete_favorite(fav_name)
                self._load_favorites_to_combobox()  
            except Exception as e:
                messagebox.showerror("Erro ao Excluir", f"{e}", parent=self.root)

    def _open_ftp_browser(self):
        site_name = self.site_combo.get()
        if not site_name: return
        try:
            site_config = self.config_manager.get_site_details(site_name)
            if not site_config.get('password'):
                messagebox.showerror("Erro de Configuração", "Não foi possível carregar senha.", parent=self.root)
                return
            
            # Chama o navegador apropriado baseado no tipo de conexão
            connection_type = site_config.get('connection_type', 'ftp')
            if connection_type == 'ssh':
                SSHBrowserWindow(self.root, site_config, self._on_file_selected_from_browser, mode='file')
            else:
                FTPBrowserWindow(self.root, site_config, self._on_file_selected_from_browser, mode='file')
            
        except Exception as e:
            messagebox.showerror("Erro ao Abrir Navegador", f"{e}", parent=self.root)
            
    def _on_file_selected_from_browser(self, selected_path: str):
        if selected_path:
            self.log_path_entry.delete(0, tk.END)
            self.log_path_entry.insert(0, selected_path)
            self._clear_favorite_selection()  

    def _open_site_manager(self):
        SiteManagerWindow(self.root, self.config_manager, self._on_site_manager_close)

    def _on_site_manager_close(self):
        """Callback que atualiza TUDO que depende dos sites."""
        self._load_sites_to_combobox()
        self._load_favorites_to_combobox()  
        self._load_sync_jobs_to_treeview() # Atualiza jobs da Aba 2
        self._clear_favorite_selection()
        if self.site_combo.get() not in self.site_combo['values']:
            self.site_combo.set("")
            self.log_path_entry.delete(0, tk.END)
            self._on_site_selected(None)

    def _start_monitoring(self):
        if self.poller_thread and self.poller_thread.is_alive():
            messagebox.showwarning("Aviso", "O monitoramento já está em execução.", parent=self.root)
            return
        site_name = self.site_combo.get()
        remote_path = self.log_path_entry.get().strip()
        if not site_name or not remote_path:
            messagebox.showerror("Erro", "Selecione um Site e um Caminho.", parent=self.root)
            return
        site_config = self.config_manager.get_site_details(site_name)
        if not site_config.get('password'):
                 messagebox.showerror("Erro", "Não foi possível carregar senha.", parent=self.root)
                 return
        try:
            # Cria o poller apropriado baseado no tipo de conexão
            connection_type = site_config.get('connection_type', 'ftp')
            if connection_type == 'ssh':
                self.poller_thread = SSHLogPoller(site_config, remote_path, self.log_tailer_queue)
            else:
                self.poller_thread = FTPLogPoller(site_config, remote_path, self.log_tailer_queue)
            self.poller_thread.start()
            self._set_tailer_ui_state(monitoring=True)
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar", f"{e}", parent=self.root)

    def _stop_monitoring(self):
        if self.poller_thread and self.poller_thread.is_alive():
            self.poller_thread.stop()
        self._set_tailer_ui_state(monitoring=False)  

    def _set_tailer_ui_state(self, monitoring: bool):
        state = tk.DISABLED if monitoring else tk.NORMAL
        browse_state = tk.NORMAL if not monitoring and self.site_combo.get() else tk.DISABLED
        self.start_btn.config(state=tk.DISABLED if monitoring else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if monitoring else tk.DISABLED)
        self.site_combo.config(state="disabled" if monitoring else "readonly")
        self.log_path_entry.config(state=state)
        self.manage_sites_btn.config(state=state)
        self.browse_btn.config(state=browse_state)
        self.fav_combo.config(state="disabled" if monitoring else "readonly")
        self.fav_save_btn.config(state=state)
        fav_del_state = tk.DISABLED if monitoring else (tk.NORMAL if self.fav_combo.get() else tk.DISABLED)
        self.fav_del_btn.config(state=fav_del_state)
        if not monitoring: self.poller_thread = None

    def _append_log_tailer(self, text: str, tag: str):
        self.log_display_tailer.configure(state=tk.NORMAL)
        if tag == "ERROR":
             self.log_display_tailer.insert(tk.END, text + '\n', (tag, "HIGHLIGHT"))
        else:
             self.log_display_tailer.insert(tk.END, text + '\n', (tag,))
        self.log_display_tailer.see(tk.END)  
        self.log_display_tailer.configure(state=tk.DISABLED)

    # --- Métodos de Menu de Contexto ---
    
    def _create_tailer_context_menu(self):
        """Cria o menu de contexto para o log do tailer."""
        self.tailer_context_menu = tk.Menu(self.root, tearoff=0)
        self.tailer_context_menu.add_command(label="Copiar", command=self._copy_selected_text)
        self.tailer_context_menu.add_command(label="Copiar Tudo", command=self._copy_log)
        self.tailer_context_menu.add_separator()
        self.tailer_context_menu.add_command(label="Limpar Log", command=self._clear_log)
        self.tailer_context_menu.add_command(label="Exportar Log...", command=self._export_log)
        self.tailer_context_menu.add_separator()
        self.tailer_context_menu.add_command(label="Selecionar Tudo", command=self._select_all_log)
    
    def _show_tailer_context_menu(self, event):
        """Mostra o menu de contexto na posição do cursor."""
        try:
            self.tailer_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tailer_context_menu.grab_release()
    
    def _copy_selected_text(self):
        """Copia o texto selecionado no log."""
        try:
            selected_text = self.log_display_tailer.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
            self.status_bar.config(text="Texto copiado.")
        except tk.TclError:
            # Nenhum texto selecionado
            self.status_bar.config(text="Nenhum texto selecionado.")
    
    def _select_all_log(self):
        """Seleciona todo o texto do log."""
        self.log_display_tailer.configure(state=tk.NORMAL)
        self.log_display_tailer.tag_add(tk.SEL, "1.0", tk.END)
        self.log_display_tailer.configure(state=tk.DISABLED)

    # --- Lógica Específica da Aba 2 (Folder Sync) ---
    
    def _load_sync_jobs_to_treeview(self):
        """Carrega as tarefas de sincronização no TreeView com indicador visual de status."""
        self.sync_jobs_tree.delete(*self.sync_jobs_tree.get_children())
        jobs = self.config_manager.get_sync_jobs()
        for name, details in jobs.items():
            # Indicador visual de status
            is_active = details.get('active', True)
            status_text = "✓ Ativo" if is_active else "✗ Inativo"
            
            self.sync_jobs_tree.insert("", "end", iid=name, text=name,  
                values=(
                    status_text,
                    details.get('site_name', 'N/A'), 
                    details.get('local_path', 'N/A'), 
                    details.get('remote_path', 'N/A')
                )
            )
        self.sync_del_btn.config(state=tk.DISABLED)

    def _on_sync_job_select(self, event):
        if self.sync_jobs_tree.focus():
            self.sync_edit_btn.config(state=tk.NORMAL)
            self.sync_del_btn.config(state=tk.NORMAL)
            self.sync_toggle_btn.config(state=tk.NORMAL)
            self.upload_all_btn.config(state=tk.NORMAL)
            # Atualiza texto do botão de toggle baseado no estado da tarefa
            self._update_toggle_button_text()
        else:
            self.sync_edit_btn.config(state=tk.DISABLED)
            self.sync_del_btn.config(state=tk.DISABLED)
            self.sync_toggle_btn.config(state=tk.DISABLED)
            self.upload_all_btn.config(state=tk.DISABLED)
    
    def _update_toggle_button_text(self):
        """Atualiza o texto do botão de toggle baseado no estado da tarefa."""
        selected_iid = self.sync_jobs_tree.focus()
        if not selected_iid:
            return
        all_jobs = self.config_manager.get_sync_jobs()
        job_details = all_jobs.get(selected_iid, {})
        is_active = job_details.get('active', True)
        self.sync_toggle_btn.config(text="Desativar" if is_active else "Ativar")

    def _add_sync_job(self):
        sites = list(self.config_manager.get_sites().keys())
        if not sites:
            messagebox.showwarning("Sem Sites", "Configure um Site (Aba 1 > Gerenciar Sites) antes de adicionar uma tarefa.", parent=self.root)
            self.notebook.select(self.tab1_frame)  
            self._open_site_manager()
            return
        SyncJobManagerWindow(self.root, self.config_manager, sites, self._load_sync_jobs_to_treeview)
    
    def _edit_sync_job(self):
        """Abre a janela para editar uma tarefa existente."""
        selected_iid = self.sync_jobs_tree.focus()
        if not selected_iid:
            return
        
        sites = list(self.config_manager.get_sites().keys())
        if not sites:
            messagebox.showwarning("Sem Sites", "Configure um Site antes de editar uma tarefa.", parent=self.root)
            return
        
        # Obtém dados atuais da tarefa
        all_jobs = self.config_manager.get_sync_jobs()
        job_details = all_jobs.get(selected_iid)
        if not job_details:
            messagebox.showerror("Erro", f"Tarefa '{selected_iid}' não encontrada.", parent=self.root)
            return
        
        # Abre a janela em modo de edição
        SyncJobManagerWindow(
            self.root, 
            self.config_manager, 
            sites, 
            self._load_sync_jobs_to_treeview,
            edit_mode=True,
            edit_job_name=selected_iid,
            edit_job_details=job_details
        )
    
    def _toggle_sync_job(self):
        """Ativa ou desativa uma tarefa de sincronização."""
        selected_iid = self.sync_jobs_tree.focus()
        if not selected_iid:
            return
        
        all_jobs = self.config_manager.get_sync_jobs()
        job_details = all_jobs.get(selected_iid)
        if not job_details:
            return
        
        # Inverte o estado
        current_active = job_details.get('active', True)
        new_active = not current_active
        
        # Atualiza no config_manager
        self.config_manager.update_sync_job_active(selected_iid, new_active)
        
        # Atualiza o indicador visual no TreeView
        status_text = "✓ Ativo" if new_active else "✗ Inativo"
        self.sync_jobs_tree.item(selected_iid, values=(
            status_text,
            job_details.get('site_name', 'N/A'),
            job_details.get('local_path', 'N/A'),
            job_details.get('remote_path', 'N/A')
        ))
        
        # Atualiza o texto do botão
        self._update_toggle_button_text()
        
        # Feedback
        status_msg = "ativada" if new_active else "desativada"
        self.status_bar.config(text=f"Tarefa '{selected_iid}' {status_msg}.")

    def _remove_sync_job(self):
        selected_iid = self.sync_jobs_tree.focus()
        if not selected_iid: return
        if messagebox.askyesno("Confirmar Exclusão", f"Excluir a tarefa '{selected_iid}'?", parent=self.root):
            try:
                self.config_manager.delete_sync_job(selected_iid)
                self._load_sync_jobs_to_treeview()  
            except Exception as e:
                messagebox.showerror("Erro ao Excluir", f"{e}", parent=self.root)

    def _start_sync_service(self):
        if self.sync_service_thread and self.sync_service_thread.is_alive():
            messagebox.showwarning("Aviso", "O serviço de sincronização já está em execução.", parent=self.root)
            return
        self.log_display_sync.configure(state=tk.NORMAL)
        self.log_display_sync.delete('1.0', tk.END)
        self.log_display_sync.configure(state=tk.DISABLED)
        all_jobs = self.config_manager.get_sync_jobs()
        job_configs = {}
        for job_name, details in all_jobs.items():
            site_name = details.get('site_name')
            site_config = self.config_manager.get_site_details(site_name)
            if not site_config.get('password'):
                self._append_log_sync(f"[{job_name}] Ignorado. Falha ao carregar senha do site '{site_name}'.", SYNC_MSG_ERROR)
                continue
            job_configs[job_name] = {**site_config, 'local_path': details.get('local_path'), 'remote_path': details.get('remote_path')}
        if not job_configs:
            self._append_log_sync("Nenhuma tarefa válida para iniciar.", SYNC_MSG_ERROR)
            return
        try:
            self.sync_service_thread = SyncService(job_configs, self.folder_sync_queue)
            self.sync_service_thread.start()
            self._set_sync_ui_state(monitoring=True)
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar Sincronização", f"{e}", parent=self.root)

    def _stop_sync_service(self):
        if self.sync_service_thread and self.sync_service_thread.is_alive():
            self.sync_service_thread.stop()
        self.sync_stop_btn.config(text="Parando...", state=tk.DISABLED)

    def _set_sync_ui_state(self, monitoring: bool):
        state = tk.DISABLED if monitoring else tk.NORMAL
        self.sync_start_btn.config(state=tk.DISABLED if monitoring else tk.NORMAL)
        self.sync_stop_btn.config(state=tk.NORMAL if monitoring else tk.DISABLED)
        self.sync_stop_btn.config(text="Parar Sincronização")  
        self.sync_add_btn.config(state=state)
        self.sync_del_btn.config(state=tk.DISABLED if monitoring else (tk.NORMAL if self.sync_jobs_tree.focus() else tk.DISABLED))
        self.upload_all_btn.config(state=tk.DISABLED if monitoring else (tk.NORMAL if self.sync_jobs_tree.focus() else tk.DISABLED))
        if not monitoring: self.sync_service_thread = None

    def _cancel_upload(self):
        """Cancela o upload em andamento."""
        self.upload_cancel_flag = True
        self.folder_sync_queue.put_nowait((SYNC_MSG_STATUS, "Cancelando upload..."))
    
    def _update_upload_progress(self, current: int, total: int, filename: str = ""):
        """Atualiza a barra de progresso do upload (chamado via root.after)."""
        if total > 0:
            percent = (current / total) * 100
            self.upload_progress_var.set(percent)
            if filename:
                self.upload_progress_label.config(text=f"{current}/{total} - {filename[:30]}...")
            else:
                self.upload_progress_label.config(text=f"{current}/{total} arquivos")
    
    def _reset_upload_progress(self):
        """Reseta a barra de progresso do upload."""
        self.upload_progress_var.set(0)
        self.upload_progress_label.config(text="")
        self.upload_in_progress = False
        self.upload_cancel_flag = False
        self.upload_all_btn.config(state=tk.NORMAL, text="Carregar Todos")
        self.upload_cancel_btn.config(state=tk.DISABLED)

    def _upload_all_files(self):
        """Faz upload de todos os arquivos da pasta local selecionada para o servidor remoto."""
        selected_iid = self.sync_jobs_tree.focus()
        if not selected_iid:
            return
        
        if self.upload_in_progress:
            messagebox.showwarning("Upload em Andamento", "Já existe um upload em andamento.", parent=self.root)
            return
        
        # Confirmação do usuário
        if not messagebox.askyesno(
            "Confirmar Upload", 
            f"Deseja fazer upload de TODOS os arquivos da tarefa '{selected_iid}' para o servidor?\n\nEsta operação pode demorar dependendo da quantidade de arquivos.",
            parent=self.root
        ):
            return
        
        # Obtém configurações da tarefa
        all_jobs = self.config_manager.get_sync_jobs()
        job_details = all_jobs.get(selected_iid)
        if not job_details:
            messagebox.showerror("Erro", f"Tarefa '{selected_iid}' não encontrada.", parent=self.root)
            return
        
        site_name = job_details.get('site_name')
        site_config = self.config_manager.get_site_details(site_name)
        if not site_config.get('password'):
            messagebox.showerror("Erro", f"Não foi possível carregar senha do site '{site_name}'.", parent=self.root)
            return
        
        local_path = job_details.get('local_path')
        remote_path = job_details.get('remote_path')
        
        if not os.path.isdir(local_path):
            messagebox.showerror("Erro", f"Pasta local '{local_path}' não existe.", parent=self.root)
            return
        
        # Configura estado inicial
        self.upload_in_progress = True
        self.upload_cancel_flag = False
        self.upload_all_btn.config(state=tk.DISABLED)
        self.upload_cancel_btn.config(state=tk.NORMAL)
        self.upload_progress_label.config(text="Preparando...")
        
        # Inicia o upload em uma thread separada usando o serviço
        upload_config = {
            **site_config,
            'local_path': local_path,
            'remote_path': remote_path,
            'job_name': selected_iid
        }
        
        upload_thread = threading.Thread(
            target=self.upload_service.bulk_upload_worker,
            args=(upload_config, self.root),
            daemon=True
        )
        upload_thread.start()

    def _clear_sync_log(self):
        """Limpa o log de sincronização."""
        self.log_display_sync.configure(state=tk.NORMAL)
        self.log_display_sync.delete('1.0', tk.END)
        self.log_display_sync.configure(state=tk.DISABLED)
        self.status_bar.config(text="Log de sincronização limpo.")

    def _append_log_sync(self, text: str, tag: str):
        self.log_display_sync.configure(state=tk.NORMAL)
        self.log_display_sync.insert(tk.END, text + '\n', (tag,))
        self.log_display_sync.see(tk.END)  
        self.log_display_sync.configure(state=tk.DISABLED)

# --- Ponto de Entrada da Aplicação ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FTPLogTailerApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Erro fatal ao iniciar a aplicação: {e}")
        messagebox.showerror("Erro Fatal", f"Não foi possível iniciar a aplicação:\n{e}")