import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from utils.resources import resource_path

class SyncJobManagerWindow(tk.Toplevel):
    """
    Janela Toplevel (modal) para adicionar ou editar
    uma nova tarefa de Sincronização de Pasta.
    """
    
    def __init__(self, parent, config_manager, site_list, on_close_callback, 
                 edit_mode=False, edit_job_name=None, edit_job_details=None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        
        # Define título baseado no modo
        self.title("Editar Tarefa de Sincronização" if edit_mode else "Adicionar Nova Tarefa de Sincronização")
        self.geometry("600x300")
        
        # (NOVO) Adiciona o ícone também nas janelas filhas
        try:
            icon_path = resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass # Ignora se falhar
        
        self.config_manager = config_manager
        self.site_list = site_list
        self.on_close_callback = on_close_callback
        
        # Modo de edição
        self.edit_mode = edit_mode
        self.edit_job_name = edit_job_name
        self.edit_job_details = edit_job_details or {}
        
        self._create_widgets()
        
        # Se está em modo de edição, preenche os campos
        if self.edit_mode and self.edit_job_details:
            self._populate_fields()
        
        self.protocol("WM_DELETE_WINDOW", self.destroy)
    
    def _populate_fields(self):
        """Preenche os campos com os dados da tarefa existente."""
        # Nome da tarefa (desabilitado em modo de edição)
        self.name_entry.insert(0, self.edit_job_name)
        self.name_entry.config(state="disabled")
        
        # Site FTP
        site_name = self.edit_job_details.get('site_name', '')
        if site_name in self.site_list:
            self.site_combo.set(site_name)
        
        # Pasta Local
        local_path = self.edit_job_details.get('local_path', '')
        self.local_path_entry.delete(0, tk.END)
        self.local_path_entry.insert(0, local_path)
        
        # Pasta Remota
        remote_path = self.edit_job_details.get('remote_path', '/')
        self.remote_path_entry.delete(0, tk.END)
        self.remote_path_entry.insert(0, remote_path)
    
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
        if self.site_list:
            self.site_combo.current(0)
        
        # Pasta Local
        ttk.Label(form_frame, text="Pasta Local (Origem):").grid(row=2, column=0, sticky=tk.W, pady=8)
        local_frame = ttk.Frame(form_frame)
        local_frame.grid(row=2, column=1, sticky=tk.EW, padx=5)
        self.local_path_entry = ttk.Entry(local_frame, width=40)
        self.local_path_entry.pack(side=tk.LEFT, fill='x', expand=True)
        self.local_browse_btn = ttk.Button(local_frame, text="Procurar...", command=self._browse_local_folder)
        self.local_browse_btn.pack(side=tk.LEFT, padx=5)
        
        # Pasta Remota
        ttk.Label(form_frame, text="Pasta Remota (Destino):").grid(row=3, column=0, sticky=tk.W, pady=8)
        remote_frame = ttk.Frame(form_frame)
        remote_frame.grid(row=3, column=1, sticky=tk.EW, padx=5)
        self.remote_path_entry = ttk.Entry(remote_frame, width=40)
        self.remote_path_entry.pack(side=tk.LEFT, fill='x', expand=True)
        self.remote_path_entry.insert(0, "/")  # Padrão
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
    
    def _browse_remote_folder(self):
        """Abre o navegador (FTP/SSH) para selecionar uma pasta de destino."""
        site_name = self.site_combo.get()
        if not site_name:
            messagebox.showwarning("Site Necessário", "Por favor, selecione um Site (Destino) primeiro.", parent=self)
            return
        
        try:
            site_config = self.config_manager.get_site_details(site_name)
            if not site_config.get('password'):
                messagebox.showerror("Erro de Configuração", f"Não foi possível carregar a senha para o site '{site_name}'.\nPor favor, re-salve a senha no Gerenciador de Sites.", parent=self)
                return
            
            # Chama o navegador apropriado baseado no tipo de conexão
            connection_type = site_config.get('connection_type', 'ftp')
            if connection_type == 'ssh':
                from ssh_browser import SSHBrowserWindow
                SSHBrowserWindow(self, site_config, self._on_remote_folder_selected, mode='directory')
            else:
                from ftp_browser import FTPBrowserWindow
                FTPBrowserWindow(self, site_config, self._on_remote_folder_selected, mode='directory')
        
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao abrir o navegador: {e}", parent=self)
    
    def _on_remote_folder_selected(self, selected_path):
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
        
        # Em modo de edição, usa o nome original
        if self.edit_mode:
            job_name = self.edit_job_name
        else:
            # Modo de adição: verifica se o nome já existe
            if job_name in self.config_manager.get_sync_jobs():
                messagebox.showerror("Erro de Validação", f"O nome de tarefa '{job_name}' já existe.", parent=self)
                return
        
        if not os.path.isdir(local_path):
            messagebox.showerror("Erro de Validação", f"A pasta local '{local_path}' não existe.", parent=self)
            return
        
        try:
            if self.edit_mode:
                # Atualiza a tarefa existente
                self.config_manager.update_sync_job(job_name, site_name, local_path, remote_path)
                messagebox.showinfo("Sucesso", f"Tarefa '{job_name}' atualizada.", parent=self)
            else:
                # Cria nova tarefa
                self.config_manager.save_sync_job(job_name, site_name, local_path, remote_path)
                messagebox.showinfo("Sucesso", f"Tarefa '{job_name}' salva.", parent=self)
            
            self.on_close_callback()  # Atualiza o Treeview na Aba 2
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"{e}", parent=self)