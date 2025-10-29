import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, scrolledtext, font
import queue
import threading

from config_manager import ConfigManager
from ftp_poller import FTPLogPoller, MSG_TYPE_LOG, MSG_TYPE_STATUS, MSG_TYPE_ERROR

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
        self._start_queue_checker()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_styles(self):
        """Define estilos e fontes customizadas."""
        self.style = ttk.Style()
        self.style.theme_use('clam') # Um tema mais limpo

        # Fonte para o log (monospaçada)
        self.log_font = font.Font(family="Consolas", size=10)
        
        # Tags de cor para o ScrolledText
        self.log_display = scrolledtext.ScrolledText(
            self.root, 
            wrap=tk.WORD, 
            font=self.log_font, 
            bg="#2b2b2b", # Fundo escuro
            fg="#cccccc"  # Texto claro
        )
        
        self.log_display.tag_configure("STATUS", foreground="#808080") # Cinza
        self.log_display.tag_configure("ERROR", foreground="#ff6347")  # Vermelho/Tomate
        self.log_display.tag_configure("LOG", foreground="#cccccc")   # Padrão (Texto claro)
        self.log_display.tag_configure("HIGHLIGHT", background="#4a4a4a") # Destaque sutil

    def _create_main_widgets(self):
        """Cria a interface principal."""
        
        # --- Frame de Configuração (Topo) ---
        config_frame = ttk.Frame(self.root, padding="10")
        config_frame.pack(fill='x')

        # Seleção de Site
        ttk.Label(config_frame, text="Site:").pack(side=tk.LEFT, padx=(0, 5))
        self.site_combo = ttk.Combobox(config_frame, state="readonly", width=30)
        self.site_combo.pack(side=tk.LEFT, padx=5)
        self.site_combo.bind("<<ComboboxSelected>>", self._on_site_selected)

        # Botão Gerenciar Sites
        self.manage_sites_btn = ttk.Button(config_frame, text="Gerenciar Sites...", command=self._open_site_manager)
        self.manage_sites_btn.pack(side=tk.LEFT, padx=5)

        # Caminho do Log
        ttk.Label(config_frame, text="Caminho do Log:").pack(side=tk.LEFT, padx=(10, 5))
        self.log_path_entry = ttk.Entry(config_frame, width=40)
        self.log_path_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        self.log_path_entry.insert(0, "/public_html/wp-content/debug.log") # Valor padrão

        # Botões de Controle
        self.start_btn = ttk.Button(config_frame, text="Iniciar", command=self._start_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(config_frame, text="Parar", command=self._stop_monitoring, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # --- Display de Log (Centro) ---
        self.log_display.pack(fill='both', expand=True, padx=10, pady=(0, 5))
        self.log_display.configure(state=tk.DISABLED) # Apenas leitura

        # --- Barra de Status (Baixo) ---
        self.status_bar = ttk.Label(self.root, text="Pronto.", padding="5", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill='x', side=tk.BOTTOM)

    def _load_sites_to_combobox(self):
        """Atualiza a lista de sites no Combobox."""
        sites = list(self.config_manager.get_sites().keys())
        self.site_combo['values'] = sites
        if sites:
            self.site_combo.current(0)
            self._on_site_selected(None) # Carrega dados do primeiro site

    def _on_site_selected(self, event):
        """Chamado quando um site é selecionado no Combobox."""
        # Em desenvolvimento futuro, poderíamos salvar o último log_path por site
        pass

    def _open_site_manager(self):
        """Abre a janela Toplevel para gerenciamento de sites."""
        SiteManagerWindow(self.root, self.config_manager, self._load_sites_to_combobox)

    def _start_monitoring(self):
        """Inicia o monitoramento (inicia a thread)."""
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
        if not site_config.get('ftp_password'): # Falha na descriptografia ou config inválida
             messagebox.showerror("Erro", f"Não foi possível carregar detalhes ou descriptografar senha para '{site_name}'.\nVerifique as configurações de criptografia ou re-salve a senha.")
             return
        
        # Limpa a tela
        self.log_display.configure(state=tk.NORMAL)
        self.log_display.delete('1.0', tk.END)
        self.log_display.configure(state=tk.DISABLED)

        # Inicia a thread
        try:
            self.poller_thread = FTPLogPoller(site_config, remote_path, self.log_queue)
            self.poller_thread.start()
            
            # Atualiza UI
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.site_combo.config(state=tk.DISABLED)
            self.log_path_entry.config(state=tk.DISABLED)
            self.manage_sites_btn.config(state=tk.DISABLED)
            self.status_bar.config(text=f"Iniciando monitoramento de '{remote_path}' em '{site_name}'...")
        
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar", f"Não foi possível iniciar a thread de monitoramento: {e}")

    def _stop_monitoring(self):
        """Para o monitoramento (para a thread)."""
        if self.poller_thread and self.poller_thread.is_alive():
            self.poller_thread.stop()
            # O poller enviará uma msg de STATUS "Parado"
        
        # Mesmo que a thread falhe em parar, resetamos a UI
        self._reset_ui_to_stopped()

    def _reset_ui_to_stopped(self):
        """Restaura o estado inicial da UI."""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.site_combo.config(state="readonly")
        self.log_path_entry.config(state=tk.NORMAL)
        self.manage_sites_btn.config(state=tk.NORMAL)
        self.status_bar.config(text="Pronto.")
        self.poller_thread = None

    def _start_queue_checker(self):
        """Inicia o loop .after() para verificar a fila (thread-safe)."""
        self.root.after(100, self._process_queue)

    def _process_queue(self):
        """Processa mensagens da fila e atualiza a UI."""
        try:
            while True: # Processa todas as mensagens pendentes
                msg_type, message = self.log_queue.get_nowait()
                
                if msg_type == MSG_TYPE_STATUS:
                    self.status_bar.config(text=message)
                    if "Monitoramento parado" in message:
                        self._reset_ui_to_stopped()
                
                elif msg_type == MSG_TYPE_ERROR:
                    self._append_log(message, "ERROR")
                    self.status_bar.config(text=f"Erro: {message}")
                
                elif msg_type == MSG_TYPE_LOG:
                    self._append_log(message, "LOG")
        
        except queue.Empty:
            # Fila vazia, normal.
            pass
        except Exception as e:
            print(f"Erro ao processar a fila: {e}")
        
        # Re-agenda a verificação
        self.root.after(200, self._process_queue) # Intervalo de 200ms

    def _append_log(self, text: str, tag: str):
        """Adiciona texto ao ScrolledText de forma segura."""
        self.log_display.configure(state=tk.NORMAL)
        
        # Adiciona highlight em linhas de erro
        if tag == "ERROR":
             self.log_display.insert(tk.END, text + '\n', (tag, "HIGHLIGHT"))
        else:
             self.log_display.insert(tk.END, text + '\n', (tag,))
        
        self.log_display.see(tk.END) # Auto-scroll
        self.log_display.configure(state=tk.DISABLED)

    def _on_closing(self):
        """Chamado ao fechar a janela principal."""
        self._stop_monitoring()
        if self.poller_thread:
            # Dá um tempo para a thread fechar
            self.poller_thread.join(timeout=1.0) 
        self.root.destroy()


class SiteManagerWindow(tk.Toplevel):
    """
    Janela Toplevel para CRUD (Criar, Ler, Atualizar, Excluir)
    das configurações de Sites FTP.
    """
    
    def __init__(self, parent, config_manager: ConfigManager, on_close_callback: callable):
        super().__init__(parent)
        self.transient(parent) # Mantém no topo
        self.grab_set() # Modal
        
        self.title("Gerenciador de Sites FTP")
        self.geometry("600x450")

        self.config_manager = config_manager
        self.on_close_callback = on_close_callback
        
        self.current_site_name = None # Para saber se estamos editando

        self._create_widgets()
        self._load_sites_to_listbox()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        # --- Lado Esquerdo (Lista de Sites) ---
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(side=tk.LEFT, fill='y', padx=(0, 10))

        ttk.Label(list_frame, text="Sites Salvos:").pack(anchor=tk.W)
        self.sites_listbox = tk.Listbox(list_frame, height=15, width=25, exportselection=False)
        self.sites_listbox.pack(fill='y', expand=True)
        self.sites_listbox.bind('<<ListboxSelect>>', self._on_listbox_select)

        # --- Lado Direito (Formulário) ---
        form_frame = ttk.Labelframe(main_frame, text="Detalhes do Site", padding="10")
        form_frame.pack(side=tk.LEFT, fill='both', expand=True)

        # Nome (Chave)
        ttk.Label(form_frame, text="Nome do Site (Único):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(form_frame, width=40)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)

        # Host
        ttk.Label(form_frame, text="FTP Host:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.host_entry = ttk.Entry(form_frame, width=40)
        self.host_entry.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Porta
        ttk.Label(form_frame, text="FTP Port:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.IntVar(value=21)
        self.port_entry = ttk.Entry(form_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Usuário
        ttk.Label(form_frame, text="FTP User:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.user_entry = ttk.Entry(form_frame, width=40)
        self.user_entry.grid(row=3, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Senha
        ttk.Label(form_frame, text="FTP Password:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.pass_entry = ttk.Entry(form_frame, width=40, show="*")
        self.pass_entry.grid(row=4, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Frame de Botões (Abaixo do formulário)
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
        """Carrega/recarrega os nomes dos sites na Listbox."""
        self.sites_listbox.delete(0, tk.END)
        sites = self.config_manager.get_sites()
        for site_name in sorted(sites.keys()):
            self.sites_listbox.insert(tk.END, site_name)

    def _on_listbox_select(self, event):
        """Ao selecionar um site na lista, preenche o formulário."""
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
            
            # A senha descriptografada
            self.pass_entry.insert(0, site_details.get('ftp_password', ''))
            
            self.delete_btn.config(state=tk.NORMAL)
            self.name_entry.config(state=tk.DISABLED) # Não permite editar a chave (Nome)

        except Exception as e:
            messagebox.showerror("Erro ao Carregar", f"Não foi possível carregar os detalhes do site: {e}", parent=self)

    def _clear_form(self, clear_name=True):
        """Limpa os campos do formulário para um novo cadastro."""
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
        if not clear_name: # Se estamos limpando após seleção, mantemos o foco
            self.host_entry.focus()
        else:
            self.name_entry.focus()

    def _save_site(self):
        """Valida e salva os dados do formulário."""
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
            # Se o nome estava desabilitado (edição), pegamos o nome original
            name_to_save = self.current_site_name if self.name_entry.cget('state') == tk.DISABLED else site_name

            # Se estamos criando um novo e o nome já existe
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
        """Exclui o site atualmente selecionado."""
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
        """Chamado ao fechar a janela de gerenciamento."""
        self.on_close_callback() # Atualiza o Combobox da janela principal
        self.grab_release()
        self.destroy()

# --- Ponto de Entrada da Aplicação ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FTPLogTailerApp(root)
        root.mainloop()
    except Exception as e:
        # Fallback para erros de inicialização (ex: Tkinter não disponível)
        print(f"Erro fatal ao iniciar a aplicação: {e}")
        messagebox.showerror("Erro Fatal", f"Não foi possível iniciar a aplicação:\n{e}")