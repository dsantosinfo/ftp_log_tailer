import sys
import os

def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funcionando em dev e no PyInstaller """
    try:
        # PyInstaller cria uma pasta temp e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Modo de desenvolvimento (não está no bundle PyInstaller)
        base_path = os.path.abspath(os.path.dirname(__file__))

    return os.path.join(base_path, relative_path)