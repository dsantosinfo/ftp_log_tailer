import tkinter as tk
from tkinter import ttk, messagebox
from ftplib import FTP, error_perm
import os
import time

class FTPBrowserWindow(tk.Toplevel):
    """
    Uma janela modal Toplevel que funciona como um navegador de arquivos
    em um servidor FTP, permitindo ao usuário selecionar um arquivo.
    """

    def __init__(self, parent, site_config: dict, on_file_select_callback: callable):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        
        self.title(f"Navegador FTP - {site_config.get('ftp_host')}")
        self.geometry("600x450")

        # Configurações e Callbacks
        self.site_config = site_config
        self.on_file_select_callback = on_file_select_callback
        
        # Estado do FTP
        self.ftp = None
        self.current_path = "/"
        
        # --- Widgets ---
        top_frame = ttk.Frame(self, padding="5")
        top_frame.pack(fill='x')

        ttk.Label(top_frame, text="Caminho:").pack(side=tk.LEFT)
        self.path_label = ttk.Label(top_frame, text=self.current_path, relief=tk.SUNKEN, anchor=tk.W, padding="2")
        self.path_label.pack(fill='x', expand=True, side=tk.LEFT, padx=5)

        # Treeview para arquivos e diretórios
        tree_frame = ttk.Frame(self, padding=(5, 0, 5, 5))
        tree_frame.pack(fill='both', expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("type", "size"), selectmode="browse")
        self.tree.heading("#0", text="Nome")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("size", text="Tamanho")
        
        self.tree.column("#0", width=300, stretch=tk.YES)
        self.tree.column("type", width=80, stretch=tk.NO, anchor=tk.CENTER)
        self.tree.column("size", width=120, stretch=tk.NO, anchor=tk.E)

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill='y')
        self.tree.pack(side=tk.LEFT, fill='both', expand=True)

        # Eventos do Treeview
        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_item_select)

        # Barra de Status
        self.status_label = ttk.Label(self, text="Conectando...", relief=tk.SUNKEN, anchor=tk.W, padding="2")
        self.status_label.pack(fill='x', side=tk.BOTTOM)

        # Botões
        button_frame = ttk.Frame(self, padding="5")
        button_frame.pack(fill='x', side=tk.BOTTOM)
        
        self.select_btn = ttk.Button(button_frame, text="Selecionar", command=self._on_select_click, state=tk.DISABLED)
        self.select_btn.pack(side=tk.RIGHT, padx=5)
        
        self.cancel_btn = ttk.Button(button_frame, text="Cancelar", command=self._close_window)
        self.cancel_btn.pack(side=tk.RIGHT)

        # --- Lógica de Inicialização ---
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        
        # Inicia a conexão e o carregamento
        self.root = parent
        self.root.update_idletasks() # Garante que a janela apareça antes de bloquear
        self._initialize_ftp()

    def _initialize_ftp(self):
        """Tenta conectar e carregar o diretório raiz."""
        if not self._connect_ftp():
            self._close_window()
            return
        
        self._load_directory(self.current_path)

    def _connect_ftp(self) -> bool:
        """Estabelece a conexão FTP."""
        self.status_label.config(text=f"Conectando a {self.site_config['ftp_host']}...")
        self.root.update_idletasks()
        try:
            self.ftp = FTP()
            self.ftp.connect(
                self.site_config['ftp_host'],
                self.site_config['ftp_port'],
                timeout=10
            )
            self.ftp.login(
                self.site_config['ftp_user'],
                self.site_config['ftp_password']
            )
            self.ftp.set_pasv(True)
            self.status_label.config(text="Conectado. Listando diretório...")
            return True
        except Exception as e:
            messagebox.showerror("Erro de Conexão FTP", f"Não foi possível conectar:\n{e}", parent=self)
            self.status_label.config(text=f"Erro de conexão: {e}")
            return False

    def _load_directory(self, path: str):
        """Limpa o Treeview e carrega o conteúdo do novo 'path'."""
        if not self.ftp:
            self.status_label.config(text="Desconectado.")
            return

        # Limpa a árvore
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.status_label.config(text=f"Listando diretório: {path}...")
        self.root.update_idletasks()

        try:
            self.ftp.cwd(path)
            self.current_path = self.ftp.pwd() # Obtém o caminho absoluto
            self.path_label.config(text=self.current_path)
            
            items = []
            
            # 1. Tenta usar MLSD (moderno, fornece fatos)
            try:
                # MLSD é um gerador
                for name, facts in self.ftp.mlsd(facts=["type", "size"]):
                    if name not in ('.', '..'):
                        items.append((name, facts))
            
            # 2. Fallback para NLST + SIZE (lento, mas compatível)
            except error_perm as e:
                if "500" in str(e): # Comando MLSD não entendido
                    self.status_label.config(text="MLSD não suportado. Usando NLST (pode ser lento)...")
                    self.root.update_idletasks()
                    names = self.ftp.nlst()
                    for name in names:
                        if name in ('.', '..'): continue
                        try:
                            # Tenta obter o tamanho (N+1 queries)
                            size = self.ftp.size(name)
                            items.append((name, {'type': 'file', 'size': size}))
                        except error_perm:
                            # Se SIZE falhar, é provável que seja um diretório
                            items.append((name, {'type': 'dir', 'size': 0}))
                else:
                    raise e # Outro erro de permissão

            # Adiciona ".." para subir
            if self.current_path != "/":
                self.tree.insert("", "end", iid="..", text=".. (Subir)", values=("dir", "<DIR>"))

            # Ordena: pastas primeiro, depois arquivos
            sorted_items = sorted(items, key=lambda x: (x[1].get('type') != 'dir', x[0].lower()))

            # Popula o Treeview
            for name, facts in sorted_items:
                item_type = facts.get('type', 'unknown')
                
                if item_type in ('dir', 'cdir', 'pdir'):
                    self.tree.insert("", "end", iid=name, text=f"📁 {name}", values=("dir", "<DIR>"))
                elif item_type == 'file':
                    size = facts.get('size', 0)
                    try:
                        size_str = f"{int(size):,} bytes" # Formata com vírgulas
                    except ValueError:
                        size_str = f"{size} bytes"
                    self.tree.insert("", "end", iid=name, text=f"📄 {name}", values=("file", size_str))

            self.status_label.config(text="Pronto.")

        except Exception as e:
            messagebox.showerror("Erro ao Listar", f"Não foi possível listar o diretório '{path}':\n{e}", parent=self)
            self.status_label.config(text=f"Erro: {e}")

    def _on_item_double_click(self, event):
        """Chamado ao dar clique duplo em um item (navega ou seleciona)."""
        selected_iid = self.tree.focus()
        if not selected_iid:
            return
            
        item_type = self.tree.set(selected_iid, "type")
        
        if item_type == "dir":
            # Navega para o diretório
            if selected_iid == "..":
                # Sobe um nível
                # Trata o caminho POSIX de forma segura
                new_path = os.path.dirname(self.current_path)
            else:
                # Desce um nível
                delimiter = "" if self.current_path == "/" else "/"
                new_path = f"{self.current_path}{delimiter}{selected_iid}"
            
            self._load_directory(new_path)
        
        elif item_type == "file":
            # Seleciona o arquivo
            self._on_select_click()

    def _on_item_select(self, event):
        """Chamado ao selecionar um item (habilita/desabilita botão)."""
        selected_iid = self.tree.focus()
        if not selected_iid:
            self.select_btn.config(state=tk.DISABLED)
            return

        item_type = self.tree.set(selected_iid, "type")
        if item_type == "file":
            self.select_btn.config(state=tk.NORMAL)
        else:
            self.select_btn.config(state=tk.DISABLED)

    def _on_select_click(self):
        """Chamado pelo botão 'Selecionar'."""
        selected_iid = self.tree.focus()
        if not selected_iid or self.tree.set(selected_iid, "type") != "file":
            return
            
        # Monta o caminho completo do arquivo
        delimiter = "" if self.current_path == "/" else "/"
        full_path = f"{self.current_path}{delimiter}{selected_iid}"
        
        # Chama o callback passado na inicialização
        self.on_file_select_callback(full_path)
        self._close_window()

    def _close_window(self):
        """Fecha a conexão FTP e destrói a janela."""
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                pass # Ignora erros ao fechar
        
        self.grab_release()
        self.destroy()