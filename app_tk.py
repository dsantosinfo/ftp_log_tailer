import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, scrolledtext, font, filedialog
import queue
import threading

from config_manager import ConfigManager
from ftp_poller import FTPLogPoller, MSG_TYPE_LOG, MSG_TYPE_STATUS, MSG_TYPE_ERROR
from ftp_browser import FTPBrowserWindow

KEY_FILE = 'secret.key'

class FTPLogTailerApp:
    """
    Aplicação principal Tkinter para o visualizador de logs FTP.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("FTP Log Tailer")
        self.root.geometry("1000x700")

        self.config_manager = ConfigManager()
        self.log_queue = queue.Queue()
        self.poller_thread = None

        self._setup_styles()
        self._create_main_widgets()
        self._load_sites_to_combobox()
        self._load_favorites_to_combobox() # NOVO
        self._start_queue_checker()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam') 

        self.log_font = font.Font(family="Consolas", size=10)
        
        self.log_display = scrolledtext.ScrolledText(
            self.root, 
            wrap=tk.WORD, 
            font=self.log_font, 
            bg="#2b2b2b",
            fg="#cccccc"
        )
        
        self.log_display.tag_configure("STATUS", foreground="#808080") 
        self.log_display.tag_configure("ERROR", foreground="#ff6347")  
        self.log_display.tag_configure("LOG", foreground="#cccccc")   
        self.log_display.tag_configure("HIGHLIGHT", background="#4a4a4a") 

    def _create_main_widgets(self):
        """Cria a interface principal (Reestruturada para Favoritos)."""
        
        # --- Frame de Configuração (Topo) ---
        config_frame = ttk.Frame(self.root, padding="10")
        config_frame.pack(fill='x')

        # --- Frame de Favoritos (Linha 1) ---
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

        # --- Frame de Controle (Linha 2) ---
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
        
        # --- Frame de Caminho (Linha 3) ---
        path_frame = ttk.Frame(config_frame, padding=(0, 10, 0, 0))
        path_frame.pack(fill='x')

        ttk.Label(path_frame, text="Caminho do Log:").pack(side=tk.LEFT, padx=(0, 5))
        self.log_path_entry = ttk.Entry(path_frame)
        self.log_path_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 5))
        self.log_path_entry.insert(0, "/public_html/wp-content/debug.log") 
        self.log_path_entry.bind("<KeyRelease>", self._on_path_entry_change) # Evento para limpar seleção de favorito

        self.browse_btn = ttk.Button(path_frame, text="Procurar...", command=self._open_ftp_browser, state=tk.DISABLED)
        self.browse_btn.pack(side=tk.LEFT)

        # --- Frame de Botões do Log (NOVO) ---
        log_btn_frame = ttk.Frame(self.root, padding=(10, 5, 10, 5))
        log_btn_frame.pack(fill='x')
        
        self.clear_log_btn = ttk.Button(log_btn_frame, text="Limpar Log", command=self._clear_log)
        self.clear_log_btn.pack(side=tk.LEFT)
        
        self.copy_log_btn = ttk.Button(log_btn_frame, text="Copiar Log", command=self._copy_log)
        self.copy_log_btn.pack(side=tk.LEFT, padx=10)
        
        self.export_log_btn = ttk.Button(log_btn_frame, text="Exportar Log...", command=self._export_log)
        self.export_log_btn.pack(side=tk.LEFT)

        # --- Display de Log (Centro) ---
        self.log_display.pack(fill='both', expand=True, padx=10, pady=(0, 5))
        self.log_display.configure(state=tk.DISABLED) 

        # --- Barra de Status (Baixo) ---
        self.status_bar = ttk.Label(self.root, text="Pronto.", padding="5", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill='x', side=tk.BOTTOM)

    # --- Funções de Carregamento e Eventos ---

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
        if favorites:
            self.fav_combo.set("") # Limpa a seleção
        self.fav_del_btn.config(state=tk.DISABLED)

    def _on_site_selected(self, event):
        if self.site_combo.get():
            self.browse_btn.config(state=tk.NORMAL)
        else:
            self.browse_btn.config(state=tk.DISABLED)
        self._clear_favorite_selection() # Limpa favorito se o site for mudado manualmente

    def _on_favorite_selected(self, event):
        """Carrega o site e o caminho ao selecionar um favorito."""
        fav_name = self.fav_combo.get()
        if not fav_name:
            self.fav_del_btn.config(state=tk.DISABLED)
            return

        favorites = self.config_manager.get_favorites()
        fav_details = favorites.get(fav_name)
        
        if fav_details:
            site_name = fav_details.get('site_name')
            remote_path = fav_details.get('remote_path')
            
            # Verifica se o site ainda existe
            if site_name not in self.config_manager.get_sites():
                messagebox.showerror("Erro de Favorito", f"O site '{site_name}' associado a este favorito não existe mais.", parent=self.root)
                self.fav_combo.set("")
                return
            
            self.site_combo.set(site_name)
            self.log_path_entry.delete(0, tk.END)
            self.log_path_entry.insert(0, remote_path)
            self.fav_del_btn.config(state=tk.NORMAL)
            self._on_site_selected(None) # Habilita o botão "Procurar"
        else:
            self.fav_del_btn.config(state=tk.DISABLED)

    def _on_path_entry_change(self, event):
        """Limpa a seleção de favorito se o usuário digitar no caminho."""
        self._clear_favorite_selection()
        
    def _clear_favorite_selection(self):
        """Limpa a seleção do combobox de favoritos."""
        if self.fav_combo.get():
            self.fav_combo.set("")
            self.fav_del_btn.config(state=tk.DISABLED)

    # --- Funções de Controle do Log (NOVAS) ---

    def _clear_log(self):
        """Limpa o widget ScrolledText."""
        self.log_display.configure(state=tk.NORMAL)
        self.log_display.delete('1.0', tk.END)
        self.log_display.configure(state=tk.DISABLED)
        self.status_bar.config(text="Log limpo.")

    def _copy_log(self):
        """Copia todo o conteúdo do log para a área de transferência."""
        try:
            log_content = self.log_display.get('1.0', tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(log_content)
            self.status_bar.config(text="Log copiado para a área de transferência.")
        except Exception as e:
            self.status_bar.config(text=f"Erro ao copiar: {e}")

    def _export_log(self):
        """Abre um diálogo 'Salvar Como' para exportar o log."""
        try:
            log_content = self.log_display.get('1.0', tk.END)
            if not log_content.strip():
                messagebox.showinfo("Log Vazio", "Não há nada para exportar.", parent=self.root)
                return

            file_path = filedialog.asksaveasfilename(
                title="Exportar Log Como...",
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("Log Files", "*.log"), ("All Files", "*.*")]
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                self.status_bar.config(text=f"Log exportado para {file_path}")
                
        except Exception as e:
            self.status_bar.config(text=f"Erro ao exportar: {e}")
            messagebox.showerror("Erro ao Exportar", f"Não foi possível salvar o arquivo:\n{e}", parent=self.root)

    # --- Funções de Gerenciamento (Favoritos, Sites, Poller) ---

    def _save_favorite(self):
        """Salva a combinação atual de site+caminho como um favorito."""
        site_name = self.site_combo.get()
        remote_path = self.log_path_entry.get().strip()
        
        if not site_name or not remote_path:
            messagebox.showwarning("Dados Incompletos", "É preciso ter um Site selecionado e um Caminho de Log preenchido para salvar um favorito.", parent=self.root)
            return

        fav_name = simpledialog.askstring(
            "Salvar Favorito", 
            "Digite um nome para este favorito:",
            parent=self.root
        )
        
        if fav_name:
            try:
                fav_name = fav_name.strip()
                self.config_manager.save_favorite(fav_name, site_name, remote_path)
                self._load_favorites_to_combobox()
                self.fav_combo.set(fav_name) # Seleciona o favorito recém-criado
                self.fav_del_btn.config(state=tk.NORMAL)
                self.status_bar.config(text=f"Favorito '{fav_name}' salvo.")
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o favorito:\n{e}", parent=self.root)

    def _delete_favorite(self):
        """Exclui o favorito atualmente selecionado."""
        fav_name = self.fav_combo.get()
        if not fav_name:
            return

        if messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir o favorito '{fav_name}'?", parent=self.root):
            try:
                self.config_manager.delete_favorite(fav_name)
                self._load_favorites_to_combobox() # Recarrega a lista
                self.status_bar.config(text=f"Favorito '{fav_name}' excluído.")
            except Exception as e:
                messagebox.showerror("Erro ao Excluir", f"Não foi possível excluir o favorito:\n{e}", parent=self.root)

    def _open_ftp_browser(self):
        site_name = self.site_combo.get()
        if not site_name:
            messagebox.showwarning("Aviso", "Por favor, selecione um site primeiro.", parent=self.root)
            return

        try:
            site_config = self.config_manager.get_site_details(site_name)
            if not site_config.get('ftp_password'):
                messagebox.showerror("Erro de Configuração", f"Não foi possível carregar detalhes ou descriptografar senha para '{site_name}'.\nRe-salve a senha no Gerenciador de Sites.", parent=self.root)
                return
            
            FTPBrowserWindow(self.root, site_config, self._on_file_selected_from_browser)
        
        except Exception as e:
            messagebox.showerror("Erro ao Abrir Navegador", f"Ocorreu um erro: {e}", parent=self.root)
            
    def _on_file_selected_from_browser(self, selected_path: str):
        if selected_path:
            self.log_path_entry.delete(0, tk.END)
            self.log_path_entry.insert(0, selected_path)
            self._clear_favorite_selection() # Limpa favorito se o caminho foi mudado
            print(f"Caminho do log selecionado: {selected_path}")

    def _open_site_manager(self):
        # Passa o callback de sites E o de favoritos, para limpar favoritos de sites excluídos
        SiteManagerWindow(self.root, self.config_manager, self._on_site_manager_close)

    def _on_site_manager_close(self):
        """Callback chamado ao fechar o gerenciador de sites."""
        self._load_sites_to_combobox()
        self._load_favorites_to_combobox() # Recarrega favoritos (caso algum site tenha sido excluído)
        self._clear_favorite_selection()
        # Limpa os campos se o site selecionado não existir mais
        if self.site_combo.get() not in self.site_combo['values']:
            self.site_combo.set("")
            self.log_path_entry.delete(0, tk.END)
            self._on_site_selected(None)


    def _start_monitoring(self):
        if self.poller_thread and self.poller_thread.is_alive():
            messagebox.showwarning("Aviso", "O monitoramento já está em execução.")
            return

        site_name = self.site_combo.get()
        remote_path = self.log_path_entry.get().strip()

        if not site_name:
            messagebox.showerror("Erro", "Por favor, selecione ou configure um site.")
            return
        if not remote_path:
            messagebox.showerror("Erro", "Por favor, insira o caminho do arquivo de log remoto.")
            return

        site_config = self.config_manager.get_site_details(site_name)
        if not site_config.get('ftp_password'):
             messagebox.showerror("Erro", f"Não foi possível carregar detalhes ou descriptografar senha para '{site_name}'.\nVerifique o {KEY_FILE} ou re-salve a senha.")
             return
        
        # Não limpa o log automaticamente, usa o botão "Limpar"
        # self._clear_log() 

        try:
            self.poller_thread = FTPLogPoller(site_config, remote_path, self.log_queue)
            self.poller_thread.start()
            
            self._set_ui_state(monitoring=True)
            self.status_bar.config(text=f"Iniciando monitoramento de '{remote_path}' em '{site_name}'...")
        
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar", f"Não foi possível iniciar a thread de monitoramento: {e}")

    def _stop_monitoring(self):
        if self.poller_thread and self.poller_thread.is_alive():
            self.poller_thread.stop()
        
        self._set_ui_state(monitoring=False) # Reseta a UI

    def _set_ui_state(self, monitoring: bool):
        """Controla o estado (habilitado/desabilitado) dos widgets."""
        state = tk.DISABLED if monitoring else tk.NORMAL
        browse_state = tk.NORMAL if not monitoring and self.site_combo.get() else tk.DISABLED
        
        # Botões de controle
        self.start_btn.config(state=tk.DISABLED if monitoring else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if monitoring else tk.DISABLED)
        
        # Controles de Configuração
        self.site_combo.config(state="disabled" if monitoring else "readonly")
        self.log_path_entry.config(state=state)
        self.manage_sites_btn.config(state=state)
        self.browse_btn.config(state=browse_state)
        
        # Controles de Favoritos
        self.fav_combo.config(state="disabled" if monitoring else "readonly")
        self.fav_save_btn.config(state=state)
        self.fav_del_btn.config(state=tk.DISABLED if monitoring else (tk.NORMAL if self.fav_combo.get() else tk.DISABLED))

        if not monitoring:
            self.status_bar.config(text="Pronto.")
            self.poller_thread = None

    def _start_queue_checker(self):
        self.root.after(100, self._process_queue)

    def _process_queue(self):
        try:
            while True: 
                msg_type, message = self.log_queue.get_nowait()
                
                if msg_type == MSG_TYPE_STATUS:
                    self.status_bar.config(text=message)
                    if "Monitoramento parado" in message:
                        self._set_ui_state(monitoring=False)
                
                elif msg_type == MSG_TYPE_ERROR:
                    self._append_log(message, "ERROR")
                    self.status_bar.config(text=f"Erro: {message}")
                
                elif msg_type == MSG_TYPE_LOG:
                    self._append_log(message, "LOG")
        
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Erro ao processar a fila: {e}")
        
        self.root.after(200, self._process_queue) 

    def _append_log(self, text: str, tag: str):
        self.log_display.configure(state=tk.NORMAL)
        
        if tag == "ERROR":
             self.log_display.insert(tk.END, text + '\n', (tag, "HIGHLIGHT"))
        else:
             self.log_display.insert(tk.END, text + '\n', (tag,))
        
        self.log_display.see(tk.END) 
        self.log_display.configure(state=tk.DISABLED)

    def _on_closing(self):
        self._stop_monitoring()
        if self.poller_thread:
            self.poller_thread.join(timeout=1.0) 
        self.root.destroy()


# (NENHUMA MUDANÇA DAQUI PARA BAIXO)
# A classe SiteManagerWindow permanece idêntica
class SiteManagerWindow(tk.Toplevel):
    
    def __init__(self, parent, config_manager: ConfigManager, on_close_callback: callable):
        super().__init__(parent)
        self.transient(parent) 
        self.grab_set() 
        
        self.title("Gerenciador de Sites FTP")
        self.geometry("600x450")

        self.config_manager = config_manager
        self.on_close_callback = on_close_callback
        
        self.current_site_name = None 

        self._create_widgets()
        self._load_sites_to_listbox()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(side=tk.LEFT, fill='y', padx=(0, 10))

        ttk.Label(list_frame, text="Sites Salvos:").pack(anchor=tk.W)
        self.sites_listbox = tk.Listbox(list_frame, height=15, width=25, exportselection=False)
        self.sites_listbox.pack(fill='y', expand=True)
        self.sites_listbox.bind('<<ListboxSelect>>', self._on_listbox_select)

        form_frame = ttk.Labelframe(main_frame, text="Detalhes do Site", padding="10")
        form_frame.pack(side=tk.LEFT, fill='both', expand=True)

        ttk.Label(form_frame, text="Nome do Site (Único):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(form_frame, width=40)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)

        ttk.Label(form_frame, text="FTP Host:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.host_entry = ttk.Entry(form_frame, width=40)
        self.host_entry.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(form_frame, text="FTP Port:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.IntVar(value=21)
        self.port_entry = ttk.Entry(form_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(form_frame, text="FTP User:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.user_entry = ttk.Entry(form_frame, width=40)
        self.user_entry.grid(row=3, column=1, sticky=tk.EW, pady=5, padx=5)
        
        ttk.Label(form_frame, text="FTP Password:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.pass_entry = ttk.Entry(form_frame, width=40, show="*")
        self.pass_entry.grid(row=4, column=1, sticky=tk.EW, pady=5, padx=5)
        
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=20)
        
        self.save_btn = ttk.Button(button_frame, text="Salvar", command=self._save_site)
        self.save_btn.pack(side=tk.LEFT, padx=10)
        
        self.delete_btn = ttk.Button(button_frame, text="Excluir", command=self._delete_site, state=tk.DISABLED)
        self.delete_btn.pack(side=tk.LEFT, padx=10)
        
        self.new_btn = ttk.Button(button_frame, text="Limpar (Novo)", command=self._clear_form)
        self.new_btn.pack(side=tk.LEFT, padx=10)
        
        form_frame.columnconfigure(1, weight=1)

    def _load_sites_to_listbox(self):
        self.sites_listbox.delete(0, tk.END)
        sites = self.config_manager.get_sites()
        for site_name in sorted(sites.keys()):
            self.sites_listbox.insert(tk.END, site_name)

    def _on_listbox_select(self, event):
        try:
            selected_indices = self.sites_listbox.curselection()
            if not selected_indices:
                return
            
            self.current_site_name = self.sites_listbox.get(selected_indices[0])
            site_details = self.config_manager.get_site_details(self.current_site_name)
            
            self._clear_form(clear_name=False)
            
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, self.current_site_name)
            
            self.host_entry.insert(0, site_details.get('ftp_host', ''))
            self.port_var.set(site_details.get('ftp_port', 21))
            self.user_entry.insert(0, site_details.get('ftp_user', ''))
            self.pass_entry.insert(0, site_details.get('ftp_password', ''))
            
            self.delete_btn.config(state=tk.NORMAL)
            self.name_entry.config(state=tk.DISABLED) 

        except Exception as e:
            messagebox.showerror("Erro ao Carregar", f"Não foi possível carregar os detalhes do site: {e}", parent=self)

    def _clear_form(self, clear_name=True):
        if clear_name:
            self.name_entry.config(state=tk.NORMAL)
            self.name_entry.delete(0, tk.END)
        
        self.host_entry.delete(0, tk.END)
        self.port_var.set(21)
        self.user_entry.delete(0, tk.END)
        self.pass_entry.delete(0, tk.END)
        
        self.sites_listbox.selection_clear(0, tk.END)
        self.delete_btn.config(state=tk.DISABLED)
        self.current_site_name = None
        if not clear_name: 
            self.host_entry.focus()
        else:
            self.name_entry.focus()

    def _save_site(self):
        site_name = self.name_entry.get().strip()
        host = self.host_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        try:
            port = self.port_var.get()
            if not (1 <= port <= 65535):
                raise ValueError
        except (tk.TclError, ValueError):
            messagebox.showerror("Erro de Validação", "A Porta deve ser um número válido (1-65535).", parent=self)
            return

        if not all([site_name, host, user, password]):
            messagebox.showerror("Erro de Validação", "Todos os campos (incluindo senha) são obrigatórios.", parent=self)
            return

        try:
            name_to_save = self.current_site_name if self.name_entry.cget('state') == tk.DISABLED else site_name

            if self.current_site_name is None and name_to_save in self.config_manager.get_sites():
                 messagebox.showerror("Erro de Validação", f"O nome '{name_to_save}' já existe. Use outro nome.", parent=self)
                 return

            self.config_manager.save_site(name_to_save, host, user, password, port)
            messagebox.showinfo("Sucesso", f"Site '{name_to_save}' salvo com sucesso.", parent=self)
            
            self._load_sites_to_listbox()
            self._clear_form()

        except ValueError as ve:
             messagebox.showerror("Erro de Validação", str(ve), parent=self)
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Ocorreu um erro: {e}", parent=self)

    def _delete_site(self):
        if not self.current_site_name:
            return

        if messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir o site '{self.current_site_name}'?", parent=self):
            try:
                self.config_manager.delete_site(self.current_site_name)
                messagebox.showinfo("Sucesso", f"Site '{self.current_site_name}' excluído.", parent=self)
                self._load_sites_to_listbox()
                self._clear_form()
            except Exception as e:
                messagebox.showerror("Erro ao Excluir", f"Ocorreu um erro: {e}", parent=self)

    def _on_close(self):
        self.on_close_callback()
        self.grab_release()
        self.destroy()

# --- Ponto de Entrada da Aplicação ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FTPLogTailerApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Erro fatal ao iniciar a aplicação: {e}")
        messagebox.showerror("Erro Fatal", f"Não foi possível iniciar a aplicação:\n{e}")