import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, scrolledtext, font, filedialog
import queue
import threading
import os
import sys # (NOVO) Importado para o resource_path

from config_manager import ConfigManager
from ftp_poller import FTPLogPoller, MSG_TYPE_LOG, MSG_TYPE_STATUS, MSG_TYPE_ERROR
from ftp_browser import FTPBrowserWindow 
from folder_watcher import SyncService, SYNC_MSG_STATUS, SYNC_MSG_SUCCESS, SYNC_MSG_ERROR

# (NOVO) FUNÇÃO PARA GARANTIR QUE O ÍCONE SEJA ENCONTRADO (DEV E EXE)
def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funcionando em dev e no PyInstaller """
    try:
        # PyInstaller cria uma pasta temp e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Modo de desenvolvimento (não está no bundle PyInstaller)
        base_path = os.path.abspath(os.path.dirname(__file__))

    return os.path.join(base_path, relative_path)

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
        self.fav_del_btn = ttk.Button(fav_frame, text="Excluir Favorito", command=self._delete_favorite, state=tk.DISABLED)
        self.fav_del_btn.pack(side=tk.LEFT, padx=5)

        control_frame = ttk.Frame(config_frame)
        control_frame.pack(fill='x')
        ttk.Label(control_frame, text="Site:").pack(side=tk.LEFT, padx=(0, 5))
        self.site_combo = ttk.Combobox(control_frame, state="readonly", width=30)
        self.site_combo.pack(side=tk.LEFT, padx=5)
        self.site_combo.bind("<<ComboboxSelected>>", self._on_site_selected)
        self.manage_sites_btn = ttk.Button(control_frame, text="Gerenciar Sites...", command=self._open_site_manager)
        self.manage_sites_btn.pack(side=tk.LEFT, padx=5)
        self.start_btn = ttk.Button(control_frame, text="Iniciar", command=self._start_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=(20, 5))
        self.stop_btn = ttk.Button(control_frame, text="Parar", command=self._stop_monitoring, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
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

    # --- Início: Aba 2 (Folder Sync) ---

    def _create_folder_sync_tab(self, parent_frame: ttk.Frame):
        sync_control_frame = ttk.Frame(parent_frame, padding=(0, 5))
        sync_control_frame.pack(fill='x')
        self.sync_start_btn = ttk.Button(sync_control_frame, text="Iniciar Sincronização", command=self._start_sync_service)
        self.sync_start_btn.pack(side=tk.LEFT)
        self.sync_stop_btn = ttk.Button(sync_control_frame, text="Parar Sincronização", command=self._stop_sync_service, state=tk.DISABLED)
        self.sync_stop_btn.pack(side=tk.LEFT, padx=10)

        sync_main_frame = ttk.Frame(parent_frame, padding=(0, 10))
        sync_main_frame.pack(fill='both', expand=True)
        
        jobs_frame = ttk.Labelframe(sync_main_frame, text="Pastas Monitoradas", padding="5")
        jobs_frame.pack(side=tk.LEFT, fill='y', padx=(0, 10))

        self.sync_jobs_tree = ttk.Treeview(jobs_frame, columns=("Site", "Local", "Remoto"), selectmode="browse", height=10)
        self.sync_jobs_tree.heading("#0", text="Nome Tarefa")
        self.sync_jobs_tree.heading("Site", text="Site FTP")
        self.sync_jobs_tree.heading("Local", text="Pasta Local")
        self.sync_jobs_tree.heading("Remoto", text="Pasta Remota")
        self.sync_jobs_tree.column("#0", width=150, stretch=tk.NO)
        self.sync_jobs_tree.column("Site", width=100, stretch=tk.NO)
        self.sync_jobs_tree.column("Local", width=250, stretch=tk.YES)
        self.sync_jobs_tree.column("Remoto", width=250, stretch=tk.YES)
        self.sync_jobs_tree.pack(fill='both', expand=True)
        self.sync_jobs_tree.bind("<<TreeviewSelect>>", self._on_sync_job_select)

        jobs_btn_frame = ttk.Frame(jobs_frame)
        jobs_btn_frame.pack(fill='x', pady=5)
        self.sync_add_btn = ttk.Button(jobs_btn_frame, text="Adicionar...", command=self._add_sync_job)
        self.sync_add_btn.pack(side=tk.LEFT)
        self.sync_del_btn = ttk.Button(jobs_btn_frame, text="Remover", command=self._remove_sync_job, state=tk.DISABLED)
        self.sync_del_btn.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.Labelframe(sync_main_frame, text="Log de Sincronização", padding="5")
        log_frame.pack(fill='both', expand=True)

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
            if not site_config.get('ftp_password'):
                messagebox.showerror("Erro de Configuração", "Não foi possível carregar senha.", parent=self.root)
                return
            
            # Chama o navegador em modo 'file'
            FTPBrowserWindow(self.root, site_config,  
                             self._on_file_selected_from_browser, mode='file')
            
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
        if not site_config.get('ftp_password'):
                 messagebox.showerror("Erro", "Não foi possível carregar senha.", parent=self.root)
                 return
        try:
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

    # --- Lógica Específica da Aba 2 (Folder Sync) ---
    
    def _load_sync_jobs_to_treeview(self):
        self.sync_jobs_tree.delete(*self.sync_jobs_tree.get_children())
        jobs = self.config_manager.get_sync_jobs()
        for name, details in jobs.items():
            self.sync_jobs_tree.insert("", "end", iid=name, text=name,  
                values=(details.get('site_name', 'N/A'), details.get('local_path', 'N/A'), details.get('remote_path', 'N/A'))
            )
        self.sync_del_btn.config(state=tk.DISABLED)

    def _on_sync_job_select(self, event):
        if self.sync_jobs_tree.focus():
            self.sync_del_btn.config(state=tk.NORMAL)
        else:
            self.sync_del_btn.config(state=tk.DISABLED)

    def _add_sync_job(self):
        sites = list(self.config_manager.get_sites().keys())
        if not sites:
            messagebox.showwarning("Sem Sites", "Configure um Site (Aba 1 > Gerenciar Sites) antes de adicionar uma tarefa.", parent=self.root)
            self.notebook.select(self.tab1_frame)  
            self._open_site_manager()
            return
        SyncJobManagerWindow(self.root, self.config_manager, sites, self._load_sync_jobs_to_treeview)

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
            if not site_config.get('ftp_password'):
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
        if not monitoring: self.sync_service_thread = None

    def _append_log_sync(self, text: str, tag: str):
        self.log_display_sync.configure(state=tk.NORMAL)
        self.log_display_sync.insert(tk.END, text + '\n', (tag,))
        self.log_display_sync.see(tk.END)  
        self.log_display_sync.configure(state=tk.DISABLED)


# (Classe SiteManagerWindow - Sem Mudanças)
# ... (código idêntico ao anterior)
class SiteManagerWindow(tk.Toplevel):
    def __init__(self, parent, config_manager: ConfigManager, on_close_callback: callable):
        super().__init__(parent)
        self.transient(parent); self.grab_set(); self.title("Gerenciador de Sites FTP"); self.geometry("600x450")
        self.config_manager = config_manager; self.on_close_callback = on_close_callback; self.current_site_name = None  
        self._create_widgets(); self._load_sites_to_listbox(); self.protocol("WM_DELETE_WINDOW", self._on_close)
    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="10"); main_frame.pack(fill='both', expand=True)
        list_frame = ttk.Frame(main_frame); list_frame.pack(side=tk.LEFT, fill='y', padx=(0, 10))
        ttk.Label(list_frame, text="Sites Salvos:").pack(anchor=tk.W)
        self.sites_listbox = tk.Listbox(list_frame, height=15, width=25, exportselection=False)
        self.sites_listbox.pack(fill='y', expand=True); self.sites_listbox.bind('<<ListboxSelect>>', self._on_listbox_select)
        form_frame = ttk.Labelframe(main_frame, text="Detalhes do Site", padding="10"); form_frame.pack(side=tk.LEFT, fill='both', expand=True)
        ttk.Label(form_frame, text="Nome do Site (Único):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(form_frame, width=40); self.name_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Label(form_frame, text="FTP Host:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.host_entry = ttk.Entry(form_frame, width=40); self.host_entry.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Label(form_frame, text="FTP Port:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.IntVar(value=21); self.port_entry = ttk.Entry(form_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Label(form_frame, text="FTP User:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.user_entry = ttk.Entry(form_frame, width=40); self.user_entry.grid(row=3, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Label(form_frame, text="FTP Password:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.pass_entry = ttk.Entry(form_frame, width=40, show="*"); self.pass_entry.grid(row=4, column=1, sticky=tk.EW, pady=5, padx=5)
        button_frame = ttk.Frame(form_frame); button_frame.grid(row=5, column=0, columnspan=2, pady=20)
        self.save_btn = ttk.Button(button_frame, text="Salvar", command=self._save_site); self.save_btn.pack(side=tk.LEFT, padx=10)
        self.delete_btn = ttk.Button(button_frame, text="Excluir", command=self._delete_site, state=tk.DISABLED)
        self.delete_btn.pack(side=tk.LEFT, padx=10)
        self.new_btn = ttk.Button(button_frame, text="Limpar (Novo)", command=self._clear_form); self.new_btn.pack(side=tk.LEFT, padx=10)
        form_frame.columnconfigure(1, weight=1)
    def _load_sites_to_listbox(self):
        self.sites_listbox.delete(0, tk.END); sites = self.config_manager.get_sites()
        for site_name in sorted(sites.keys()): self.sites_listbox.insert(tk.END, site_name)
    def _on_listbox_select(self, event):
        try:
            selected_indices = self.sites_listbox.curselection();
            if not selected_indices: return
            self.current_site_name = self.sites_listbox.get(selected_indices[0])
            site_details = self.config_manager.get_site_details(self.current_site_name); self._clear_form(clear_name=False)
            self.name_entry.delete(0, tk.END); self.name_entry.insert(0, self.current_site_name)
            self.host_entry.insert(0, site_details.get('ftp_host', '')); self.port_var.set(site_details.get('ftp_port', 21))
            self.user_entry.insert(0, site_details.get('ftp_user', '')); self.pass_entry.insert(0, site_details.get('ftp_password', ''))
            self.delete_btn.config(state=tk.NORMAL); self.name_entry.config(state=tk.DISABLED)  
        except Exception as e: messagebox.showerror("Erro ao Carregar", f"{e}", parent=self)
    def _clear_form(self, clear_name=True):
        if clear_name: self.name_entry.config(state=tk.NORMAL); self.name_entry.delete(0, tk.END)
        self.host_entry.delete(0, tk.END); self.port_var.set(21); self.user_entry.delete(0, tk.END); self.pass_entry.delete(0, tk.END)
        self.sites_listbox.selection_clear(0, tk.END); self.delete_btn.config(state=tk.DISABLED); self.current_site_name = None; self.name_entry.focus()
    def _save_site(self):
        site_name = self.name_entry.get().strip(); host = self.host_entry.get().strip(); user = self.user_entry.get().strip(); password = self.pass_entry.get().strip()
        try: port = self.port_var.get()
        except (tk.TclError, ValueError): messagebox.showerror("Erro de Validação", "Porta deve ser um número.", parent=self); return
        if not all([site_name, host, user, password]): messagebox.showerror("Erro de Validação", "Todos os campos são obrigatórios.", parent=self); return
        try:
            name_to_save = self.current_site_name if self.name_entry.cget('state') == tk.DISABLED else site_name
            if self.current_site_name is None and name_to_save in self.config_manager.get_sites():
                 messagebox.showerror("Erro de Validação", f"O nome '{name_to_save}' já existe.", parent=self); return
            self.config_manager.save_site(name_to_save, host, user, password, port); messagebox.showinfo("Sucesso", f"Site '{name_to_save}' salvo.", parent=self)
            self._load_sites_to_listbox(); self._clear_form()
        except Exception as e: messagebox.showerror("Erro ao Salvar", f"{e}", parent=self)
    def _delete_site(self):
        if not self.current_site_name: return
        if messagebox.askyesno("Confirmar Exclusão", f"Excluir o site '{self.current_site_name}'?\n(Isso também excluirá Favoritos e Tarefas de Sincronização associados a ele)", parent=self):
            try:
                self.config_manager.delete_site(self.current_site_name); messagebox.showinfo("Sucesso", f"Site '{self.current_site_name}' excluído.", parent=self)
                self._load_sites_to_listbox(); self._clear_form()
            except Exception as e: messagebox.showerror("Erro ao Excluir", f"{e}", parent=self)
    def _on_close(self): self.on_close_callback(); self.grab_release(); self.destroy()


# (CLASSE MODIFICADA) Janela Modal para Adicionar/Editar Sync Job
class SyncJobManagerWindow(tk.Toplevel):
    """
    Janela Toplevel (modal) para adicionar ou editar
    uma nova tarefa de Sincronização de Pasta.
    """
    
    def __init__(self, parent, config_manager: ConfigManager, site_list: list, on_close_callback: callable):
        super().__init__(parent)
        self.transient(parent)  
        self.grab_set()  
        self.title("Adicionar Nova Tarefa de Sincronização")
        self.geometry("600x300")

        self.config_manager = config_manager
        self.site_list = site_list
        self.on_close_callback = on_close_callback
        
        self._create_widgets()
        
        # (NOVO) Adiciona o ícone também nas janelas filhas
        try:
            icon_path = resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass # Ignora se falhar
        
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _create_widgets(self):
        form_frame = ttk.Frame(self, padding="15")
        form_frame.pack(fill='both', expand=True)
        form_frame.columnconfigure(1, weight=1)

        # Nome da Tarefa
        ttk.Label(form_frame, text="Nome da Tarefa (Único):").grid(row=0, column=0, sticky=tk.W, pady=8)
        self.name_entry = ttk.Entry(form_frame, width=50)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, pady=8, padx=5)

        # Site FTP
        ttk.Label(form_frame, text="Site FTP (Destino):").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.site_combo = ttk.Combobox(form_frame, state="readonly", values=self.site_list)
        self.site_combo.grid(row=1, column=1, sticky=tk.EW, pady=8, padx=5)
        if self.site_list: self.site_combo.current(0)

        # Pasta Local
        ttk.Label(form_frame, text="Pasta Local (Origem):").grid(row=2, column=0, sticky=tk.W, pady=8)
        local_frame = ttk.Frame(form_frame)  
        local_frame.grid(row=2, column=1, sticky=tk.EW, padx=5)
        self.local_path_entry = ttk.Entry(local_frame, width=40)
        self.local_path_entry.pack(side=tk.LEFT, fill='x', expand=True)
        self.local_browse_btn = ttk.Button(local_frame, text="Procurar...", command=self._browse_local_folder)
        self.local_browse_btn.pack(side=tk.LEFT, padx=5)

        # Pasta Remota (MODIFICADO)
        ttk.Label(form_frame, text="Pasta Remota (Destino):").grid(row=3, column=0, sticky=tk.W, pady=8)
        remote_frame = ttk.Frame(form_frame) # Frame para Entry + Botão
        remote_frame.grid(row=3, column=1, sticky=tk.EW, padx=5)
        self.remote_path_entry = ttk.Entry(remote_frame, width=40)
        self.remote_path_entry.pack(side=tk.LEFT, fill='x', expand=True)
        self.remote_path_entry.insert(0, "/") # Padrão
        self.remote_browse_btn = ttk.Button(remote_frame, text="Procurar...", command=self._browse_remote_folder)
        self.remote_browse_btn.pack(side=tk.LEFT, padx=5)
        
        # Botões
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20)
        self.save_btn = ttk.Button(button_frame, text="Salvar Tarefa", command=self._save_job)
        self.save_btn.pack(side=tk.LEFT, padx=10)
        self.cancel_btn = ttk.Button(button_frame, text="Cancelar", command=self.destroy)
        self.cancel_btn.pack(side=tk.LEFT, padx=10)

    def _browse_local_folder(self):
        dir_path = filedialog.askdirectory(title="Selecione a Pasta Local para Monitorar")
        if dir_path:
            self.local_path_entry.delete(0, tk.END)
            self.local_path_entry.insert(0, os.path.normpath(dir_path).replace("\\", "/"))

    # (NOVO) Função para o botão "Procurar..." da pasta remota
    def _browse_remote_folder(self):
        """Abre o navegador FTP para selecionar uma pasta de destino."""
        site_name = self.site_combo.get()
        if not site_name:
            messagebox.showwarning("Site Necessário", "Por favor, selecione um Site FTP (Destino) primeiro.", parent=self)
            return

        try:
            site_config = self.config_manager.get_site_details(site_name)
            if not site_config.get('ftp_password'):
                messagebox.showerror("Erro de Configuração", f"Não foi possível carregar a senha para o site '{site_name}'.\nPor favor, re-salve a senha no Gerenciador de Sites.", parent=self)
                return
            
            # Chama o navegador em modo 'directory'
            FTPBrowserWindow(self, site_config,  
                             self._on_remote_folder_selected, mode='directory')
        
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao abrir o navegador FTP: {e}", parent=self)

    # (NOVO) Callback para o navegador de pasta remota
    def _on_remote_folder_selected(self, selected_path: str):
        """Atualiza o campo de entrada com o caminho da pasta selecionada."""
        if selected_path:
            self.remote_path_entry.delete(0, tk.END)
            self.remote_path_entry.insert(0, selected_path)
            # Traz o foco de volta para a janela modal
            self.lift()
            self.grab_set()

    def _save_job(self):
        job_name = self.name_entry.get().strip()
        site_name = self.site_combo.get()
        local_path = self.local_path_entry.get().strip()
        remote_path = self.remote_path_entry.get().strip()
        if not all([job_name, site_name, local_path, remote_path]):
            messagebox.showerror("Erro de Validação", "Todos os campos são obrigatórios.", parent=self)
            return
        if job_name in self.config_manager.get_sync_jobs():
            messagebox.showerror("Erro de Validação", f"O nome de tarefa '{job_name}' já existe.", parent=self)
            return
        if not os.path.isdir(local_path):
             messagebox.showerror("Erro de Validação", f"A pasta local '{local_path}' não existe.", parent=self)
             return
        try:
            self.config_manager.save_sync_job(job_name, site_name, local_path, remote_path)
            messagebox.showinfo("Sucesso", f"Tarefa '{job_name}' salva.", parent=self)
            self.on_close_callback() # Atualiza o Treeview na Aba 2
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"{e}", parent=self)


# --- Ponto de Entrada da Aplicação ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FTPLogTailerApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Erro fatal ao iniciar a aplicação: {e}")
        messagebox.showerror("Erro Fatal", f"Não foi possível iniciar a aplicação:\n{e}")