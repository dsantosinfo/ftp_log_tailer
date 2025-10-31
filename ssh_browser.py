import tkinter as tk
from tkinter import ttk, messagebox
import paramiko
import stat
import os

class SSHBrowserWindow(tk.Toplevel):
    """
    Uma janela modal Toplevel que funciona como um navegador de arquivos
    em um servidor SSH, permitindo ao usuário selecionar um ARQUIVO ou DIRETÓRIO.
    """

    def __init__(self, parent, site_config: dict, 
                 on_select_callback: callable, mode: str = 'file'):
        """
        Inicializa o navegador SSH.
        
        Args:
            parent: A janela pai.
            site_config: Dicionário com detalhes da conexão (host, user, pass, etc).
            on_select_callback: Função a ser chamada com o caminho selecionado.
            mode: 'file' (seleciona arquivos) ou 'directory' (seleciona diretórios).
        """
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        
        self.title(f"Navegador SSH - {site_config.get('host')}")
        self.geometry("600x450")

        # Configurações e Callbacks
        self.site_config = site_config
        self.on_select_callback = on_select_callback
        self.mode = mode # 'file' or 'directory'
        
        # Estado do SSH
        self.ssh = None
        self.sftp = None
        self.current_path = "/"
        
        # --- Widgets ---
        top_frame = ttk.Frame(self, padding="5")
        top_frame.pack(fill='x')

        ttk.Label(top_frame, text="Caminho:").pack(side=tk.LEFT)
        self.path_label = ttk.Label(top_frame, text=self.current_path, relief=tk.SUNKEN, anchor=tk.W, padding="2")
        self.path_label.pack(fill='x', expand=True, side=tk.LEFT, padx=5)

        # Treeview
        tree_frame = ttk.Frame(self, padding=(5, 0, 5, 5))
        tree_frame.pack(fill='both', expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("type", "size"), selectmode="browse")
        self.tree.heading("#0", text="Nome")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("size", text="Tamanho")
        self.tree.column("#0", width=300, stretch=tk.YES)
        self.tree.column("type", width=80, stretch=tk.NO, anchor=tk.CENTER)
        self.tree.column("size", width=120, stretch=tk.NO, anchor=tk.E)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill='y')
        self.tree.pack(side=tk.LEFT, fill='both', expand=True)

        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_item_select)

        # Barra de Status
        self.status_label = ttk.Label(self, text="Conectando...", relief=tk.SUNKEN, anchor=tk.W, padding="2")
        self.status_label.pack(fill='x', side=tk.BOTTOM)

        # Botões
        button_frame = ttk.Frame(self, padding="5")
        button_frame.pack(fill='x', side=tk.BOTTOM)
        
        btn_text = "Selecionar Pasta" if self.mode == 'directory' else "Selecionar Arquivo"
        self.select_btn = ttk.Button(button_frame, text=btn_text, command=self._on_select_click, state=tk.DISABLED)
        self.select_btn.pack(side=tk.RIGHT, padx=5)
        
        self.cancel_btn = ttk.Button(button_frame, text="Cancelar", command=self._close_window)
        self.cancel_btn.pack(side=tk.RIGHT)

        # --- Lógica de Inicialização ---
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.root = parent
        self.root.update_idletasks()
        self._initialize_ssh()

    def _initialize_ssh(self):
        if not self._connect_ssh():
            self._close_window()
            return
        self._load_directory(self.current_path)

    def _connect_ssh(self) -> bool:
        self.status_label.config(text=f"Conectando a {self.site_config['host']}...")
        self.root.update_idletasks()
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.site_config['host'],
                port=self.site_config['port'],
                username=self.site_config['user'],
                password=self.site_config['password'],
                timeout=10
            )
            self.sftp = self.ssh.open_sftp()
            self.status_label.config(text="Conectado. Listando diretório...")
            return True
        except Exception as e:
            messagebox.showerror("Erro de Conexão SSH", f"Não foi possível conectar:\n{e}", parent=self)
            return False

    def _load_directory(self, path: str):
        if not self.sftp: return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_label.config(text=f"Listando diretório: {path}...")
        self.root.update_idletasks()

        try:
            # Normaliza o caminho
            if path != "/":
                path = path.rstrip("/")
            self.current_path = path if path else "/"
            self.path_label.config(text=self.current_path)
            
            items = []
            
            # Lista arquivos e diretórios
            for item in self.sftp.listdir_attr(self.current_path):
                if item.filename not in ('.', '..'):
                    items.append(item)

            # Adiciona ".." para subir
            if self.current_path != "/":
                self.tree.insert("", "end", iid="..", text=".. (Subir)", values=("dir", "<DIR>"))

            # Ordena: diretórios primeiro, depois arquivos
            sorted_items = sorted(items, key=lambda x: (not stat.S_ISDIR(x.st_mode), x.filename.lower()))

            for item in sorted_items:
                if stat.S_ISDIR(item.st_mode):
                    self.tree.insert("", "end", iid=item.filename, text=f"📁 {item.filename}", values=("dir", "<DIR>"))
                else:
                    size_str = f"{item.st_size:,} bytes" if item.st_size else "0 bytes"
                    self.tree.insert("", "end", iid=item.filename, text=f"📄 {item.filename}", values=("file", size_str))

            self.status_label.config(text="Pronto.")
            # Habilita o botão se o modo for 'directory'
            if self.mode == 'directory':
                self.select_btn.config(state=tk.NORMAL)

        except Exception as e:
            messagebox.showerror("Erro ao Listar", f"Não foi possível listar '{path}':\n{e}", parent=self)
            self.status_label.config(text=f"Erro: {e}")

    def _on_item_double_click(self, event):
        selected_iid = self.tree.focus()
        if not selected_iid: return
        item_type = self.tree.set(selected_iid, "type")
        
        if item_type == "dir":
            # Navega para o diretório
            if selected_iid == "..":
                new_path = os.path.dirname(self.current_path) if self.current_path != "/" else "/"
            else:
                new_path = os.path.join(self.current_path, selected_iid).replace("\\", "/")
                if not new_path.startswith("/"):
                    new_path = "/" + new_path
            self._load_directory(new_path)
        
        elif item_type == "file" and self.mode == 'file':
            # Se for modo 'file', duplo clique seleciona
            self._on_select_click()

    def _on_item_select(self, event):
        """Habilita/desabilita botão com base no modo."""
        selected_iid = self.tree.focus()
        if not selected_iid:
            if self.mode == 'directory':
                self.select_btn.config(state=tk.NORMAL)
            else:
                self.select_btn.config(state=tk.DISABLED)
            return

        item_type = self.tree.set(selected_iid, "type")
        
        # Habilita o botão se o item selecionado corresponder ao modo
        if (self.mode == 'file' and item_type == 'file') or \
           (self.mode == 'directory' and item_type == 'dir'):
            self.select_btn.config(state=tk.NORMAL)
        else:
            if self.mode == 'directory':
                self.select_btn.config(state=tk.NORMAL)
            else:
                self.select_btn.config(state=tk.DISABLED)

    def _on_select_click(self):
        """Chamado pelo botão 'Selecionar'."""
        selected_iid = self.tree.focus()
        
        # Modo de seleção de DIRETÓRIO
        if self.mode == 'directory':
            path_to_return = self.current_path
            # Se um subdiretório estiver focado (e não for '..'), anexa-o
            if selected_iid and self.tree.set(selected_iid, "type") == 'dir' and selected_iid != '..':
                path_to_return = os.path.join(self.current_path, selected_iid).replace("\\", "/")
                if not path_to_return.startswith("/"):
                    path_to_return = "/" + path_to_return
            
            self.on_select_callback(path_to_return)
            self._close_window()
            return

        # Modo de seleção de ARQUIVO
        if self.mode == 'file':
            if not selected_iid or self.tree.set(selected_iid, "type") != 'file':
                messagebox.showwarning("Seleção Inválida", "Por favor, selecione um ARQUIVO.", parent=self)
                return
            
            full_path = os.path.join(self.current_path, selected_iid).replace("\\", "/")
            if not full_path.startswith("/"):
                full_path = "/" + full_path
            self.on_select_callback(full_path)
            self._close_window()
            return

    def _close_window(self):
        if self.sftp:
            try: self.sftp.close()
            except Exception: pass
        if self.ssh:
            try: self.ssh.close()
            except Exception: pass
        self.grab_release()
        self.destroy()