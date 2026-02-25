import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from utils.resources import resource_path

class SiteManagerWindow(tk.Toplevel):
    def __init__(self, parent, config_manager, on_close_callback):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Gerenciador de Sites (FTP/SSH)")
        self.geometry("600x500")
        
        # (NOVO) Adiciona o ícone também nas janelas filhas
        try:
            icon_path = resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass # Ignora se falhar
        
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
        
        # Nome do Site
        ttk.Label(form_frame, text="Nome do Site (Único):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(form_frame, width=40)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Tipo de Conexão
        ttk.Label(form_frame, text="Tipo de Conexão:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.connection_type_var = tk.StringVar(value="ftp")
        connection_frame = ttk.Frame(form_frame)
        connection_frame.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        
        self.ftp_radio = ttk.Radiobutton(connection_frame, text="FTP", variable=self.connection_type_var, value="ftp", command=self._on_connection_type_change)
        self.ftp_radio.pack(side=tk.LEFT, padx=(0, 10))
        
        self.ssh_radio = ttk.Radiobutton(connection_frame, text="SSH", variable=self.connection_type_var, value="ssh", command=self._on_connection_type_change)
        self.ssh_radio.pack(side=tk.LEFT)
        
        # Host
        ttk.Label(form_frame, text="Host:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.host_entry = ttk.Entry(form_frame, width=40)
        self.host_entry.grid(row=2, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Porta
        ttk.Label(form_frame, text="Porta:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.IntVar(value=21)
        self.port_entry = ttk.Entry(form_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Usuário
        ttk.Label(form_frame, text="Usuário:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.user_entry = ttk.Entry(form_frame, width=40)
        self.user_entry.grid(row=4, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Senha
        ttk.Label(form_frame, text="Senha:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.pass_entry = ttk.Entry(form_frame, width=40, show="*")
        self.pass_entry.grid(row=5, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # Botões
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=20)
        
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
    
    def _on_connection_type_change(self):
        """Atualiza a porta padrão quando o tipo de conexão muda."""
        if self.connection_type_var.get() == "ssh":
            if self.port_var.get() == 21:  # Se ainda está na porta padrão do FTP
                self.port_var.set(22)
        else:  # FTP
            if self.port_var.get() == 22:  # Se ainda está na porta padrão do SSH
                self.port_var.set(21)
    
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
            
            self.connection_type_var.set(site_details.get('connection_type', 'ftp'))
            self.host_entry.insert(0, site_details.get('host', ''))
            self.port_var.set(site_details.get('port', 21))
            self.user_entry.insert(0, site_details.get('user', ''))
            self.pass_entry.insert(0, site_details.get('password', ''))
            
            self.delete_btn.config(state=tk.NORMAL)
            self.name_entry.config(state="disabled")  # Não permite editar o nome
        except Exception as e:
            messagebox.showerror("Erro ao Carregar", f"{e}", parent=self)
    
    def _clear_form(self, clear_name=True):
        if clear_name:
            self.name_entry.config(state="normal")
            self.name_entry.delete(0, tk.END)
        
        self.connection_type_var.set("ftp")
        self.host_entry.delete(0, tk.END)
        self.port_var.set(21)
        self.user_entry.delete(0, tk.END)
        self.pass_entry.delete(0, tk.END)
        
        self.sites_listbox.selection_clear(0, tk.END)
        self.delete_btn.config(state=tk.DISABLED)
        self.current_site_name = None
        self.name_entry.focus()
    
    def _save_site(self):
        site_name = self.name_entry.get().strip()
        host = self.host_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        connection_type = self.connection_type_var.get()
        
        try:
            port = self.port_var.get()
        except (tk.TclError, ValueError):
            messagebox.showerror("Erro de Validação", "Porta deve ser um número.", parent=self)
            return
        
        if not all([site_name, host, user, password]):
            messagebox.showerror("Erro de Validação", "Todos os campos são obrigatórios.", parent=self)
            return
        
        try:
            name_to_save = self.current_site_name if self.name_entry.cget('state') == "disabled" else site_name
            
            if self.current_site_name is None and name_to_save in self.config_manager.get_sites():
                messagebox.showerror("Erro de Validação", f"O nome '{name_to_save}' já existe.", parent=self)
                return
            
            self.config_manager.save_site(name_to_save, host, user, password, port, connection_type)
            messagebox.showinfo("Sucesso", f"Site '{name_to_save}' salvo.", parent=self)
            
            self._load_sites_to_listbox()
            self._clear_form()
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"{e}", parent=self)
    
    def _delete_site(self):
        if not self.current_site_name:
            return
        
        if messagebox.askyesno("Confirmar Exclusão", f"Excluir o site '{self.current_site_name}'?\n(Isso também excluirá Favoritos e Tarefas de Sincronização associados a ele)", parent=self):
            try:
                self.config_manager.delete_site(self.current_site_name)
                messagebox.showinfo("Sucesso", f"Site '{self.current_site_name}' excluído.", parent=self)
                self._load_sites_to_listbox()
                self._clear_form()
            except Exception as e:
                messagebox.showerror("Erro ao Excluir", f"{e}", parent=self)
    
    def _on_close(self):
        self.on_close_callback()
        self.grab_release()
        self.destroy()