import tkinter as tk
from tkinter import ttk, messagebox
from ftplib import FTP, error_perm
import os
import time

class FTPBrowserWindow(tk.Toplevel):
    """
    Uma janela modal Toplevel que funciona como um navegador de arquivos
    em um servidor FTP, permitindo ao usuário selecionar um ARQUIVO ou DIRETÓRIO.
    """

    def __init__(self, parent, site_config: dict, 
                 on_select_callback: callable, mode: str = 'file'):
        """
        Inicializa o navegador FTP.
        
        Args:
            parent: A janela pai.
            site_config: Dicionário com detalhes da conexão (host, user, pass, etc).
            on_select_callback: Função a ser chamada com o caminho selecionado.
            mode: 'file' (seleciona arquivos) ou 'directory' (seleciona diretórios).
        """
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        
        self.title(f"Navegador FTP - {site_config.get('ftp_host')}")
        self.geometry("600x450")

        # Configurações e Callbacks
        self.site_config = site_config
        self.on_select_callback = on_select_callback
        self.mode = mode # 'file' or 'directory'
        
        # Estado do FTP
        self.ftp = None
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
        self._initialize_ftp()

    def _initialize_ftp(self):
        if not self._connect_ftp():
            self._close_window()
            return
        self._load_directory(self.current_path)

    def _connect_ftp(self) -> bool:
        self.status_label.config(text=f"Conectando a {self.site_config['ftp_host']}...")
        self.root.update_idletasks()
        try:
            self.ftp = FTP()
            self.ftp.connect(self.site_config['ftp_host'], self.site_config['ftp_port'], timeout=10)
            self.ftp.login(self.site_config['ftp_user'], self.site_config['ftp_password'])
            self.ftp.set_pasv(True)
            self.status_label.config(text="Conectado. Listando diretório...")
            return True
        except Exception as e:
            messagebox.showerror("Erro de Conexão FTP", f"Não foi possível conectar:\n{e}", parent=self)
            return False

    def _load_directory(self, path: str):
        if not self.ftp: return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_label.config(text=f"Listando diretório: {path}...")
        self.root.update_idletasks()

        try:
            self.ftp.cwd(path)
            self.current_path = self.ftp.pwd()
            self.path_label.config(text=self.current_path)
            items = []
            
            try:
                for name, facts in self.ftp.mlsd(facts=["type", "size"]):
                    if name not in ('.', '..'):
                        items.append((name, facts))
            except error_perm:
                # Fallback para NLST + SIZE (lento)
                self.status_label.config(text="MLSD não suportado. Usando NLST (lento)...")
                self.root.update_idletasks()
                names = self.ftp.nlst()
                for name in names:
                    if name in ('.', '..'): continue
                    try:
                        size = self.ftp.size(name)
                        items.append((name, {'type': 'file', 'size': size}))
                    except error_perm:
                        items.append((name, {'type': 'dir', 'size': 0}))

            # Adiciona ".." para subir
            if self.current_path != "/":
                self.tree.insert("", "end", iid="..", text=".. (Subir)", values=("dir", "<DIR>"))

            sorted_items = sorted(items, key=lambda x: (x[1].get('type') != 'dir', x[0].lower()))

            for name, facts in sorted_items:
                item_type = facts.get('type', 'unknown')
                if item_type in ('dir', 'cdir', 'pdir'):
                    self.tree.insert("", "end", iid=name, text=f"📁 {name}", values=("dir", "<DIR>"))
                elif item_type == 'file':
                    size = facts.get('size', 0)
                    try: size_str = f"{int(size):,} bytes"
                    except ValueError: size_str = f"{size} bytes"
                    self.tree.insert("", "end", iid=name, text=f"📄 {name}", values=("file", size_str))

            self.status_label.config(text="Pronto.")
            # (NOVO) Habilita o botão se o modo for 'directory' e estivermos no raiz
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
                new_path = os.path.dirname(self.current_path)
            else:
                delimiter = "" if self.current_path == "/" else "/"
                new_path = f"{self.current_path}{delimiter}{selected_iid}"
            self._load_directory(new_path)
        
        elif item_type == "file" and self.mode == 'file':
            # Se for modo 'file', duplo clique seleciona
            self._on_select_click()

    def _on_item_select(self, event):
        """Habilita/desabilita botão com base no modo."""
        selected_iid = self.tree.focus()
        if not selected_iid:
            # (NOVO) Se nada estiver selecionado, mas o modo for 'directory',
            # permite selecionar o diretório atual.
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
            # (NOVO) Se modo 'directory' e um arquivo for selecionado,
            # ainda permitimos selecionar o diretório PAI (o atual).
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
                delimiter = "" if self.current_path == "/" else "/"
                path_to_return = f"{self.current_path}{delimiter}{selected_iid}"
            
            self.on_select_callback(path_to_return)
            self._close_window()
            return

        # Modo de seleção de ARQUIVO (comportamento antigo)
        if self.mode == 'file':
            if not selected_iid or self.tree.set(selected_iid, "type") != 'file':
                messagebox.showwarning("Seleção Inválida", "Por favor, selecione um ARQUIVO.", parent=self)
                return
            
            delimiter = "" if self.current_path == "/" else "/"
            full_path = f"{self.current_path}{delimiter}{selected_iid}"
            self.on_select_callback(full_path)
            self._close_window()
            return

    def _close_window(self):
        if self.ftp:
            try: self.ftp.quit()
            except Exception: pass 
        self.grab_release()
        self.destroy()