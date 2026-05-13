import sys
import os
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from functools import partial

import cv2
import numpy as np

from PyQt6.QtCore import (
    Qt, QSize, QTimer, QUrl, QPoint, QSettings, 
    QThread, pyqtSignal, QEvent
)

from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QImage, QDesktopServices
)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, 
    QStyle, QCheckBox, QDialog, QVBoxLayout, QHBoxLayout, 
    QListWidget, QListWidgetItem, QLineEdit, QTextEdit, 
    QMessageBox, QComboBox, QTabWidget, QScrollArea, 
    QFrame, QSizePolicy, QFileDialog, QProgressBar
)

def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para o PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def find_catalog_file(filename="catalogo_erros.json"):
    """ Procura o arquivo de catálogo em localizações comuns (raiz, Exemplos, BENIAN). """
    search_paths = [
        resource_path(filename),
        resource_path(os.path.join("Exemplos", filename)),
        resource_path(os.path.join("BENIAN", filename))
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            return path
    
    return search_paths[0]

class ColorFiltersDialog(QDialog):
    """ Diálogo não modal que permite ao usuário selecionar e aplicar filtros de processamento de imagem em tempo real. """
    def __init__(self, parent=None):
        """ Inicializa o diálogo, configura a referência à janela pai e constrói a interface. """
        super().__init__(parent)
        self.parent_window = parent
        self.init_ui()

        restore_dialog_position(self, "ColorFiltersDialog/pos")
        
    def init_ui(self):
        """ Configura o layout, estilos e conecta os checkboxes aos métodos de filtro. """
        self.setWindowTitle("Filtros de Visualização")
        self.setFixedSize(300, 280)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QCheckBox { 
                color: white; font-size: 14px; padding: 8px; spacing: 10px;
            }
            QCheckBox::indicator { width: 20px; height: 20px; }
            QCheckBox::indicator:unchecked {
                border: 2px solid #6a6a6a; background-color: #3a3a3a; border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #00ff00; background-color: #00ff00; border-radius: 3px;
            }
        """)
        
        layout = QVBoxLayout()
        
        title = QLabel("Selecione o Filtro")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        self.filters = {
            'normal': QCheckBox("Normal"),
            'invert': QCheckBox("Inverter Cores"),
            'high_contrast': QCheckBox("Alto Contraste"),
            'bright': QCheckBox("Mais Brilhante"),
            'dark': QCheckBox("Mais Escuro")
        }
        
        for key, checkbox in self.filters.items():
            layout.addWidget(checkbox)
            checkbox.clicked.connect(lambda checked, k=key: self.set_filter(k))
            
        layout.addStretch()
        self.setLayout(layout)
    
    def set_filter(self, filter_type):
        """ Gerencia a exclusividade dos checkboxes e solicita à janela pai a aplicação do filtro selecionado. """
        self.blockSignals(True)
        for chk in self.filters.values():
            chk.setChecked(False)
        self.filters[filter_type].setChecked(True)
        self.blockSignals(False)
        
        if self.parent_window:
            self.parent_window.apply_image_filter(filter_type)
            
    def restore_current_filter(self, filter_type):
        """ Atualiza visualmente o estado dos checkboxes sem disparar eventos, útil ao reabrir a janela. """
        if filter_type in self.filters:
            self.blockSignals(True)
            for chk in self.filters.values():
                chk.setChecked(False)
            self.filters[filter_type].setChecked(True)
            self.blockSignals(False)

    def closeEvent(self, event):
        """ Salva a posição da janela antes de fechar. """
        SETTINGS.setValue("ColorFiltersDialog/pos", self.pos())
        super().closeEvent(event)

    def hideEvent(self, event):
        """ Salva a posição quando a janela é ocultada. """
        SETTINGS.setValue("ColorFiltersDialog/pos", self.pos())
        super().hideEvent(event)

SETTINGS = QSettings("BenIanDev", "BenIan")

def center_dialog_on_screen(dialog):
    """Centraliza o dialogo na tela do pai, respeitando a area disponivel."""
    parent = dialog.parentWidget()
    screen = parent.screen() if parent and parent.screen() else QApplication.primaryScreen()
    geometry = screen.availableGeometry()
    x = geometry.x() + (geometry.width() - dialog.width()) // 2
    y = geometry.y() + (geometry.height() - dialog.height()) // 2
    dialog.move(x, y)

def restore_dialog_position(dialog, settings_key, center_if_invalid=True):
    """Restaura a posicao salva apenas se ela ainda estiver visivel."""
    pos = SETTINGS.value(settings_key, None)
    if isinstance(pos, QPoint):
        width = max(dialog.width(), 80)
        height = max(dialog.height(), 80)
        for screen in QApplication.screens():
            geometry = screen.availableGeometry()
            if (
                pos.x() + width > geometry.left()
                and pos.x() < geometry.right()
                and pos.y() + height > geometry.top()
                and pos.y() < geometry.bottom()
            ):
                dialog.move(pos)
                return

        SETTINGS.remove(settings_key)

    if center_if_invalid:
        center_dialog_on_screen(dialog)

from functools import partial
class ZipLoaderThread(QThread):
    """ Thread responsável por extrair o arquivo ZIP em segundo plano e organizar a lista de mídias, evitando o congelamento da interface. """
    progress = pyqtSignal(int, str)  
    finished = pyqtSignal(list) 
    error = pyqtSignal(str) 
    
    def __init__(self, zip_path, temp_dir):
        """ Configura os caminhos de entrada e saída e define as extensões válidas para busca. """
        super().__init__()
        self.zip_path = zip_path
        self.temp_dir = temp_dir
        self.valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff'}
        self.labels_set = {'dedao', 'indic', 'anel', 'medio', 'mind'}

    def run(self):
        """ Executa o processo de extração e organização, emitindo sinais de progresso, erro ou conclusão. """
        try:
            self.progress.emit(0, "Iniciando extração...")
            
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                
                for i, member in enumerate(file_list):
                    zip_ref.extract(member, self.temp_dir)
                    percent = int(((i + 1) / total_files) * 100)
                    self.progress.emit(percent, f"Extraindo: {member}")
            
            self.progress.emit(100, "Organizando arquivos...")
            media_files = self.organize_files()
            self.finished.emit(media_files)
            
        except Exception as e:
            self.error.emit(str(e))
    
    def organize_files(self):
        """ Varre o diretório temporário, identifica arquivos de imagem válidos e extrai metadados (ID, data, dedo) baseados na estrutura de pastas e nomes de arquivo. """
        media_files = []
        
        zip_year_month = self.extract_year_month(os.path.basename(self.zip_path))
        zip_ano, zip_mes = zip_year_month if zip_year_month else ("????", "??")
        
        all_files = []
        
        for root, _, files in os.walk(self.temp_dir):
            for file in files:
                if os.path.splitext(file)[1].lower() not in self.valid_extensions:
                    continue
                    
                file_path = os.path.join(root, file)
                
                relative_path = file_path.replace(self.temp_dir, '').strip(os.sep)
                path_parts = relative_path.split(os.sep)
                
                pastas_do_arquivo = path_parts[:-1]
                ano, mes, idx_ano_mes = self.extract_year_month_from_parts(pastas_do_arquivo)
                if not ano:
                    ano, mes = zip_ano, zip_mes

                dia = self.extract_day_from_parts(pastas_do_arquivo, idx_ano_mes)
                data_formatada = f"{dia}/{mes}/{ano}"
                if "?" in data_formatada:
                    data_por_timestamp = self.extract_date_from_filename_timestamp(file)
                    if data_por_timestamp:
                        data_formatada = data_por_timestamp
                id_folder = path_parts[-2] if len(path_parts) >= 2 else "Unknown"
                
                nome_sem_ext = os.path.splitext(file)[0]
                dedo_formatado = self.extract_dedo_info(nome_sem_ext)
                frame_numero = self.extract_frame_info(nome_sem_ext)
                
                all_files.append({
                    'file_path': file_path,
                    'filename': file,
                    'nome_sem_ext': nome_sem_ext,
                    'data': data_formatada,
                    'id': id_folder,
                    'dedo': dedo_formatado,
                    'frame': frame_numero
                })

        all_files.sort(key=lambda x: (x['data'], x['id'], x['filename']))
        return all_files

    @staticmethod
    def extract_year_month(text):
        """ Extrai ano e mes em formatos como 2024-02, 2024_02, 2024 02 ou 202402. """
        match = re.search(r'(?<!\d)((?:19|20)\d{2})[ _-]?([01]\d)(?!\d)', text)
        if not match:
            return None

        year, month = match.groups()
        if 1 <= int(month) <= 12:
            return year, month
        return None

    def extract_year_month_from_parts(self, path_parts):
        """ Procura ano/mes em cada pasta do caminho relativo do arquivo. """
        for idx, part in enumerate(path_parts):
            result = self.extract_year_month(part)
            if result:
                year, month = result
                return year, month, idx
        return None, None, None

    @staticmethod
    def normalize_day(part):
        """ Normaliza dia para dois digitos quando o nome da pasta representa 1..31. """
        if re.fullmatch(r'\d{1,2}', part):
            value = int(part)
            if 1 <= value <= 31:
                return f"{value:02d}"
        return "??"

    def extract_day_from_parts(self, path_parts, year_month_index):
        """ Prioriza a pasta apos ano/mes como dia; se nao existir, tenta outra pasta numerica. """
        if year_month_index is not None and (year_month_index + 1) < len(path_parts):
            day = self.normalize_day(path_parts[year_month_index + 1])
            if day != "??":
                return day

        for part in reversed(path_parts):
            day = self.normalize_day(part)
            if day != "??":
                return day

        return "??"

    @staticmethod
    def extract_date_from_filename_timestamp(filename):
        """ Fallback: converte timestamp Unix no nome do arquivo para dd/mm/YYYY. """
        match = re.search(r'(?<!\d)(1\d{9}|2\d{9})(?:\.\d+)?(?!\d)', filename)
        if not match:
            return None

        try:
            dt = datetime.fromtimestamp(int(match.group(1)))
            return dt.strftime("%d/%m/%Y")
        except (OverflowError, OSError, ValueError):
            return None
    
    def extract_frame_info(self, filename):
        """ Utiliza Expressões Regulares (Regex) para identificar e extrair o número do frame no nome do arquivo. """

        match = re.search(r'_frame_(\d+)', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0
    
    def extract_dedo_info(self, filename):
        """ Analisa o nome do arquivo para determinar qual dedo e mão (ex: 'dedao_d') a imagem representa. """
        parts = filename.lower().split('_')
        finger_map = {
            'dedao': 'Dedão', 'indic': 'Indicador', 
            'medio': 'Médio', 'anel': 'Anelar', 'mind': 'Mindinho'
        }
        side_map = {'d': 'Direita', 'e': 'Esquerda'}
        
        found_finger = ""
        found_side = ""
        
        for part in parts:
            if part in finger_map: found_finger = finger_map[part]
            if part in ['d', 'e']: found_side = side_map[part]
            if len(part) == 2 and part[0].isdigit() and part[1] in ['d', 'e']:
                found_side = side_map[part[1]]
        
        if found_finger and found_side:
            return f"{found_finger} - {found_side}"
        return found_finger or "Desconhecido"

class ProgressDialog(QDialog):
    """ Janela modal simples contendo uma barra de progresso para bloquear a interação durante operações longas. """
    def __init__(self, parent=None):
        """ Inicializa o diálogo de progresso com barra e label de status. """
        super().__init__(parent)
        self.setWindowTitle("Carregando...")
        self.setFixedSize(300, 100)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.setStyleSheet("background-color: #2b2b2b; color: white;")
        
        layout = QVBoxLayout()
        self.status_label = QLabel("Iniciando...")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 2px solid grey; border-radius: 5px; text-align: center; } QProgressBar::chunk { background-color: #0080FF; }")
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def update_progress(self, val, text):
        """ Atualiza o valor da barra e o texto de status; fecha o diálogo automaticamente ao atingir 100%. """
        self.progress_bar.setValue(val)
        self.status_label.setText(text)
        if val >= 100: self.accept()

class AvaliacaoDialog(QDialog):
    """ Diálogo complexo que exibe os erros selecionados e permite ao usuário atribuir uma nota (estrelas) para cada um. """
    def __init__(self, parent=None, erros_selecionados=None):
        """ Inicializa o diálogo com a lista de erros e prepara o sistema de avaliação por estrelas. """
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.parent_window = parent
        self.erros_selecionados = erros_selecionados or []
        self.avaliacoes = {}
        for i, erro in enumerate(self.erros_selecionados):
            try:
                avaliacao = int(erro.get('avaliacao', 0))
            except (TypeError, ValueError):
                avaliacao = 0
            if avaliacao > 0:
                self.avaliacoes[i] = avaliacao
        
        self.setUpdatesEnabled(False)
        
        self.setWindowTitle("Avaliação dos Erros")
        self.setMinimumSize(800, 600)
        self.setMaximumSize(1000, 800)
        
        self.cached_styles = self.prepare_cached_styles()
        
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        
        self.init_ui()
        
        self.setUpdatesEnabled(True)
        
        restore_dialog_position(self, "AvaliacaoDialog/pos")

    def prepare_cached_styles(self):
        """ Retorna um dicionário com strings de estilo CSS pré-definidas para otimizar a criação da interface. """
        return {
            'dialog': """
                QDialog { background-color: #2b2b2b; color: white; }
                QLabel { color: white; font-size: 14px; font-weight: bold; }
                QPushButton { background-color: #4a4a4a; border: 1px solid #6a6a6a; border-radius: 5px; padding: 8px 15px; color: white; font-size: 12px; }
                QPushButton:hover { background-color: #5a5a5a; }
                QPushButton:pressed { background-color: #3a3a3a; }
                QScrollArea { border: 1px solid #5a5a5a; border-radius: 5px; background-color: #3a3a3a; }
                QFrame { background-color: #3a3a3a; border: 1px solid #5a5a5a; border-radius: 5px; margin: 5px; padding: 10px; }
            """,
            'frame': """
                QFrame { background-color: #4a4a4a; border: 2px solid #6a6a6a; border-radius: 8px; margin: 5px; padding: 15px; }
            """,
            'estrela_acesa': """
                QPushButton { background-color: transparent; border: none; color: #FFD700; font-size: 36px; font-weight: bold; padding: 0px; margin: 0px; }
                QPushButton:hover { color: #FFD700; background-color: rgba(255, 215, 0, 0.2); border-radius: 30px; }
            """,
            'estrela_apagada': """
                QPushButton { background-color: transparent; border: none; color: #0f0f0f; font-size: 36px; font-weight: normal; padding: 0px; margin: 0px; }
                QPushButton:hover { color: #FFD700; background-color: rgba(255, 215, 0, 0.2); border-radius: 30px; }
            """
        }

    def init_ui(self):
        """ Constrói a interface dinâmica baseada na quantidade de erros selecionados, escolhendo entre renderização total ou progressiva. """
        self.blockSignals(True)
        
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        self.setStyleSheet(self.cached_styles['dialog'])
        
        title_label = QLabel("Avalie cada erro individualmente:")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; margin-bottom: 20px;")
        self.main_layout.addWidget(title_label)
        
        if not self.erros_selecionados:
            no_errors_label = QLabel("Nenhum erro foi selecionado.\nSelecione erros primeiro usando o botão 'Erro'.")
            no_errors_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_errors_label.setStyleSheet("font-size: 16px; color: #ff6666; margin: 50px;")
            self.main_layout.addWidget(no_errors_label)
        else:
            if len(self.erros_selecionados) <= 5:
                self.create_all_erros_at_once()
            else:
                self.create_scroll_area()
                QTimer.singleShot(1, self.create_erros_progressively_fast) 

        self.create_buttons()
        self.blockSignals(False)

    def create_all_erros_at_once(self):
        """ Cria todos os widgets de erro de uma vez; usado quando há poucos erros para exibir. """
        self.create_scroll_area()
        for i, erro in enumerate(self.erros_selecionados):
            erro_frame = self.create_erro_frame_optimized(i, erro)
            self.scroll_layout.addWidget(erro_frame)
            self.atualizar_estrelas_display(i)
            self.atualizar_label_avaliacao(i)
        QApplication.processEvents()

    def create_scroll_area(self):
        """ Configura a área de rolagem onde os itens de avaliação serão inseridos. """
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(self.scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        self.main_layout.addWidget(scroll_area)

    def create_erros_progressively_fast(self):
        """ Cria os widgets de erro em lotes usando QTimer para manter a interface responsiva se houver muitos itens. """
        if not hasattr(self, 'erro_index_atual'):
            self.erro_index_atual = 0
        
        erros_por_lote = min(20, len(self.erros_selecionados) - self.erro_index_atual)
        
        for _ in range(erros_por_lote):
            if self.erro_index_atual < len(self.erros_selecionados):
                erro = self.erros_selecionados[self.erro_index_atual]
                erro_frame = self.create_erro_frame_optimized(self.erro_index_atual, erro)
                self.scroll_layout.addWidget(erro_frame)
                self.atualizar_estrelas_display(self.erro_index_atual)
                self.atualizar_label_avaliacao(self.erro_index_atual)
                self.erro_index_atual += 1
        
        if self.erro_index_atual < len(self.erros_selecionados):
            QTimer.singleShot(1, self.create_erros_progressively_fast)
        else:
            QApplication.processEvents()

    def create_erro_frame_optimized(self, index, erro):
        """ Fabrica o widget visual (Frame) de um único erro, contendo título, descrição e o sistema de estrelas. """
        frame = QFrame()
        frame.setStyleSheet(self.cached_styles['frame'])
        layout = QVBoxLayout()
        
        nome_label = QLabel(f"Erro: {erro['nome']}")
        nome_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFD700; margin-bottom: 5px;")
        layout.addWidget(nome_label)
        
        desc_label = QLabel(f"Descrição: {erro['descricao']}")
        desc_label.setStyleSheet("font-size: 14px; color: #cccccc; margin-bottom: 15px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        stars_layout = QHBoxLayout()
        stars_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stars_layout.setSpacing(20)
        
        estrelas = []
        for i in range(5):
            estrela = QPushButton("☆") 
            estrela.setFixedSize(60, 60)
            estrela.setStyleSheet(self.cached_styles['estrela_apagada'])
            
            estrela.enterEvent = self.create_hover_handler(index, i)
            estrela.leaveEvent = self.create_leave_handler(index)
            estrela.clicked.connect(self.create_click_handler(index, i))
            
            stars_layout.addWidget(estrela)
            estrelas.append(estrela)
        
        frame.estrelas = estrelas
        frame.erro_index = index
        layout.addLayout(stars_layout)
        
        avaliacao_label = QLabel("Avaliação: Não avaliado")
        avaliacao_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avaliacao_label.setStyleSheet("font-size: 12px; color: #00ff00; margin-top: 10px;")
        frame.avaliacao_label = avaliacao_label
        layout.addWidget(avaliacao_label)
        
        frame.setLayout(layout)
        return frame

    def create_hover_handler(self, erro_index, estrela_index):
        """ Factory method para criar eventos de hover (passar o mouse) personalizados para as estrelas. """
        return lambda event: self.on_estrela_hover(erro_index, estrela_index)

    def create_leave_handler(self, erro_index):
        """ Factory method para restaurar o estado visual das estrelas quando o mouse sai do componente. """
        return lambda event: self.on_mouse_leave_estrelas(erro_index)

    def create_click_handler(self, erro_index, estrela_index):
        """ Factory method para registrar a nota clicada pelo usuário. """
        return lambda: self.on_estrela_click(erro_index, estrela_index)

    def create_buttons(self):
        """ Adiciona os botões de confirmação e cancelamento ao layout principal. """
        buttons_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_cancel)
        
        btn_ok = QPushButton("Confirmar Avaliações")
        btn_ok.setStyleSheet("QPushButton { background-color: #0080FF; font-weight: bold; } QPushButton:hover { background-color: #3399FF; }")
        btn_ok.clicked.connect(self.accept)
        buttons_layout.addWidget(btn_ok)
        self.main_layout.addLayout(buttons_layout)

    def get_estrela_style(self, acesa=False):
        """ Retorna o estilo CSS apropriado para uma estrela acesa ou apagada. """
        return self.cached_styles['estrela_acesa'] if acesa else self.cached_styles['estrela_apagada']
    
    def on_estrela_hover(self, erro_index, estrela_index):
        """ Atualiza visualmente as estrelas em tempo real enquanto o usuário move o mouse. """
        frame = self.find_frame_by_index(erro_index)
        if frame:
            estrelas = frame.estrelas
            for i in range(5):
                if i <= estrela_index:
                    estrelas[i].setText("★")
                    estrelas[i].setStyleSheet(self.get_estrela_style(True))
                else:
                    estrelas[i].setText("☆")
                    estrelas[i].setStyleSheet(self.get_estrela_style(False))
    
    def on_mouse_leave_estrelas(self, erro_index):
        """ Reseta a visualização das estrelas para refletir a nota salva (ou nenhuma) ao tirar o mouse. """
        self.atualizar_estrelas_display(erro_index)
    
    def on_estrela_click(self, erro_index, estrela_index):
        """ Salva a avaliação interna e atualiza a interface permanentemente para aquela seleção. """
        self.avaliacoes[erro_index] = estrela_index + 1
        self.atualizar_estrelas_display(erro_index)
        self.atualizar_label_avaliacao(erro_index)
    
    def atualizar_estrelas_display(self, erro_index):
        """ Renderiza o estado atual das estrelas de um erro específico. """
        frame = self.find_frame_by_index(erro_index)
        if frame:
            estrelas = frame.estrelas
            avaliacao = self.avaliacoes.get(erro_index, 0)
            for i in range(5):
                if i < avaliacao:
                    estrelas[i].setText("★")
                    estrelas[i].setStyleSheet(self.get_estrela_style(True))
                else:
                    estrelas[i].setText("☆")
                    estrelas[i].setStyleSheet(self.get_estrela_style(False))
    
    def atualizar_label_avaliacao(self, erro_index):
        """ Atualiza o texto descritivo (ex: '3/5') abaixo das estrelas. """
        frame = self.find_frame_by_index(erro_index)
        if frame:
            avaliacao = self.avaliacoes.get(erro_index, 0)
            if avaliacao > 0:
                estrelas_texto = "★" * avaliacao
                frame.avaliacao_label.setText(f"Avaliação: {estrelas_texto} ({avaliacao}/5)")
            else:
                frame.avaliacao_label.setText("Avaliação: Não avaliado")
    
    def find_frame_by_index(self, erro_index):
        """ Busca na árvore de widgets o frame correspondente ao índice do erro para atualizações visuais. """
        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            scroll_widget = scroll_area.widget()
            for child in scroll_widget.findChildren(QFrame):
                if hasattr(child, 'erro_index') and child.erro_index == erro_index:
                    return child
        return None
    
    def center_on_screen(self):
        """ Calcula a geometria da tela e centraliza o diálogo. """
        center_dialog_on_screen(self)
    
    def get_avaliacoes(self):
        """ Retorna um dicionário contendo todas as notas atribuídas até o momento. """
        return dict(self.avaliacoes)
    
    def todas_avaliacoes_preenchidas(self):
        """ Valida se todos os erros listados receberam uma nota maior que zero. """
        return len(self.avaliacoes) == len(self.erros_selecionados) and all(av > 0 for av in self.avaliacoes.values())

    def restaurar_avaliacoes(self, avaliacoes_salvas):
        """ Reaplica avaliações prévias ao reabrir o diálogo, restaurando o estado visual. """
        if not avaliacoes_salvas: return
        for erro_index, avaliacao in avaliacoes_salvas.items():
            idx = int(erro_index)
            if idx < len(self.erros_selecionados):
                self.avaliacoes[idx] = avaliacao
                self.atualizar_estrelas_display(idx)
                self.atualizar_label_avaliacao(idx)

    def accept(self):
        """ Salva a posição e aceita o diálogo. """
        SETTINGS.setValue("AvaliacaoDialog/pos", self.pos())
        super().accept()

    def reject(self):
        """ Salva a posição e rejeita o diálogo. """
        SETTINGS.setValue("AvaliacaoDialog/pos", self.pos())
        super().reject()

    def closeEvent(self, event):
        """ Salva a posição da janela antes de fechar. """
        SETTINGS.setValue("AvaliacaoDialog/pos", self.pos())
        super().closeEvent(event)

    def hideEvent(self, event):
        """ Salva a posição quando a janela é ocultada. """
        SETTINGS.setValue("AvaliacaoDialog/pos", self.pos())
        super().hideEvent(event)

class ErroDialog(QDialog):
    """ Diálogo não modal para seleção de erros do catálogo personalizado com validação de correspondência entre nomes e descrições. """
    def __init__(self, parent=None, custom_errors=None):
        """ Inicializa o diálogo de seleção de erros com o catálogo de erros personalizado e configura a interface. """
        super().__init__(parent)
        self.setWindowTitle("Selecionar Erros")
        self.setFixedSize(700, 600)
        self.custom_errors = custom_errors or {}
        self.selected_names = []
        self.selected_descriptions = []

        # Janela não-modal para permitir interação com a imagem
        self.setModal(False)
        self.apply_styles()
        self.init_ui()

        # Restaurar seleção anterior
        self.restaurar_selecao()
        
        restore_dialog_position(self, "ErroDialog/pos")
    
    def apply_styles(self):
        """ Define o tema visual escuro do diálogo e estilos para todos os componentes da interface. """
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: white; font-size: 14px; font-weight: bold; }
            QPushButton { background-color: #4a4a4a; border: 1px solid #6a6a6a; border-radius: 5px; padding: 8px 15px; color: white; font-size: 12px; min-width: 80px; }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
            QListWidget { background-color: #3a3a3a; border: 1px solid #5a5a5a; border-radius: 5px; color: white; font-size: 12px; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #4a4a4a; background-color: transparent; }
            QListWidget::item:selected { background-color: #0080FF; color: white; }
            QListWidget::item:hover { background-color: #4a4a4a; }
            QListWidget::item:selected:hover { background-color: #3399FF; color: white; }
            QTabWidget::pane { border: 1px solid #5a5a5a; background-color: #2b2b2b; }
            QTabBar::tab { background-color: #4a4a4a; color: white; padding: 8px 15px; margin-right: 2px; border-top-left-radius: 5px; border-top-right-radius: 5px; }
            QTabBar::tab:selected { background-color: #0080FF; }
            QTabBar::tab:hover { background-color: #5a5a5a; }
        """)
    
    def init_ui(self):
        """ Constrói a interface com abas de nomes e descrições, listas de seleção e botões de ação. """
        main_layout = QVBoxLayout()
        
        title_label = QLabel("Selecionar Erros para Análise")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title_label)
        
        self.tab_widget = QTabWidget()
        
        nomes_widget = QWidget()
        l_nomes = QVBoxLayout(nomes_widget)
        l_nomes.addWidget(QLabel("Nomes de Erro Disponíveis"))
        self.list_names = QListWidget()
        self.list_names.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        nomes = self.custom_errors.get("nomes", [])
        for nome in nomes:
            item = QListWidgetItem(nome)
            item.setData(Qt.ItemDataRole.UserRole, nome)
            self.list_names.addItem(item)
            
        self.list_names.itemSelectionChanged.connect(self.on_names_selection_changed)
        l_nomes.addWidget(self.list_names)
        self.label_count_names = QLabel("Nenhum nome selecionado")
        self.label_count_names.setStyleSheet("font-size: 11px; color: #00FF00; margin-top: 5px;")
        l_nomes.addWidget(self.label_count_names)
        self.tab_widget.addTab(nomes_widget, "Nomes")
        
        desc_widget = QWidget()
        l_desc = QVBoxLayout(desc_widget)
        l_desc.addWidget(QLabel("Descrições Correspondentes"))
        self.instrucao_desc = QLabel("Selecione nomes na aba anterior...")
        self.instrucao_desc.setStyleSheet("font-size: 11px; color: #cccccc; margin-bottom: 10px;")
        l_desc.addWidget(self.instrucao_desc)
        
        self.list_descriptions = QListWidget()
        self.list_descriptions.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list_descriptions.itemSelectionChanged.connect(self.on_descriptions_selection_changed)
        l_desc.addWidget(self.list_descriptions)
        
        self.label_count_desc = QLabel("Nenhuma descrição disponível")
        self.label_count_desc.setStyleSheet("font-size: 11px; color: #00FF00; margin-top: 5px;")
        l_desc.addWidget(self.label_count_desc)
        self.tab_widget.addTab(desc_widget, "Descrições")
        
        main_layout.addWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        btn_layout = QHBoxLayout()
        btn_clear = QPushButton("Limpar Tudo")
        btn_clear.clicked.connect(self.clear_all_selections)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_ok = QPushButton("Confirmar Seleção")
        btn_ok.setStyleSheet("QPushButton { background-color: #0080FF; font-weight: bold; } QPushButton:hover { background-color: #3399FF; }")
        btn_ok.clicked.connect(self.validate_and_accept) 
        btn_layout.addWidget(btn_ok)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def on_tab_changed(self, index):
        """ Atualiza a lista de descrições quando o usuário muda para a aba de descrições. """
        if index == 1: self.update_descriptions()

    def on_names_selection_changed(self):
        count = len(self.list_names.selectedItems())
        self.label_count_names.setText(f"{count} nome(s) selecionado(s)")
        self.update_descriptions()

    def on_descriptions_selection_changed(self):
        """ Atualiza o contador de descrições selecionadas para feedback visual ao usuário. """
        count = len(self.list_descriptions.selectedItems())
        self.label_count_desc.setText(f"{count} descrição(ões) selecionada(s)")

    def update_descriptions(self):
        """ Filtra e exibe apenas as descrições correspondentes aos nomes de erro selecionados. """
        current_selected = [item.data(Qt.ItemDataRole.UserRole) for item in self.list_descriptions.selectedItems()]
        self.list_descriptions.clear()
        
        selected_names = [item.data(Qt.ItemDataRole.UserRole) for item in self.list_names.selectedItems()]
        if not selected_names:
            self.instrucao_desc.setText("Selecione nomes na aba anterior...")
            return

        self.instrucao_desc.setText(f"Descrições para: {', '.join(selected_names[:3])}...")
        desc_obj = self.custom_errors.get("descricoes", {})
        
        for nome in selected_names:
            for desc in desc_obj.get(nome, []):
                item_text = f"[{nome}] {desc[:50]}..."
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, (nome, desc))
                item.setToolTip(desc)
                self.list_descriptions.addItem(item)
                if (nome, desc) in current_selected: item.setSelected(True)
                
        self.label_count_desc.setText(f"{self.list_descriptions.count()} disponíveis")

    def clear_all_selections(self):
        """ Remove todas as seleções de nomes e descrições, resetando o formulário. """
        self.list_names.clearSelection()
        self.list_descriptions.clearSelection()

    def center_on_screen(self):
        """ Centraliza o diálogo na tela principal do usuário. """
        center_dialog_on_screen(self)

    def get_selections(self):
        """ Retorna uma tupla contendo listas vazias de nomes e tuplas (nome, descrição) das descrições selecionadas. """
        return ([], [item.data(Qt.ItemDataRole.UserRole) for item in self.list_descriptions.selectedItems()])

    def accept(self):
        """ Salva a posição e a seleção atual antes de aceitar o diálogo. """
        SETTINGS.setValue("ErroDialog/pos", self.pos())
        self.salvar_selecao_atual()
        super().accept()

    def reject(self):
        """ Salva a posição e a seleção atual antes de rejeitar o diálogo. """
        SETTINGS.setValue("ErroDialog/pos", self.pos())
        self.salvar_selecao_atual()
        super().reject()

    def closeEvent(self, event):
        """ Salva a posição da janela nas configurações antes de fechar. """
        SETTINGS.setValue("ErroDialog/pos", self.pos())
        self.salvar_selecao_atual()
        super().closeEvent(event)

    def hideEvent(self, event):
        """ Salva a posição quando a janela é ocultada. """
        SETTINGS.setValue("ErroDialog/pos", self.pos())
        self.salvar_selecao_atual()
        super().hideEvent(event)

    def salvar_selecao_atual(self):
        """ Salva os nomes e descrições selecionados atualmente. """
        nomes_selecionados = [item.data(Qt.ItemDataRole.UserRole) for item in self.list_names.selectedItems()]
        descricoes_selecionadas = [item.data(Qt.ItemDataRole.UserRole) for item in self.list_descriptions.selectedItems()]

        SETTINGS.setValue("ErroDialog/selected_names", nomes_selecionados)
        SETTINGS.setValue("ErroDialog/selected_descriptions", descricoes_selecionadas)

    def restaurar_selecao(self):
        """ Restaura a seleção anterior de nomes e descrições. """
        nomes_salvos = SETTINGS.value("ErroDialog/selected_names", [])
        descricoes_salvas = SETTINGS.value("ErroDialog/selected_descriptions", [])

        if not nomes_salvos:
            return

        for i in range(self.list_names.count()):
            item = self.list_names.item(i)
            nome = item.data(Qt.ItemDataRole.UserRole)
            if nome in nomes_salvos:
                item.setSelected(True)

        self.update_descriptions()

        if isinstance(descricoes_salvas, list):
            for i in range(self.list_descriptions.count()):
                item = self.list_descriptions.item(i)
                desc_data = item.data(Qt.ItemDataRole.UserRole)
                if desc_data in descricoes_salvas:
                    item.setSelected(True)
    
    def validate_and_accept(self):
        """ Valida se cada nome selecionado possui ao menos uma descrição correspondente selecionada. """
        nomes_selecionados = [item.data(Qt.ItemDataRole.UserRole) for item in self.list_names.selectedItems()]
        
        if not nomes_selecionados:
            self.reject()
            return

        descricoes_data = [item.data(Qt.ItemDataRole.UserRole) for item in self.list_descriptions.selectedItems()]
        
        nomes_com_descricao = {dado[0] for dado in descricoes_data}
        
        pendentes = []
        for nome in nomes_selecionados:
            if nome not in nomes_com_descricao:
                pendentes.append(nome)
        
        if pendentes:
            msg = "Você selecionou os seguintes erros mas não escolheu a descrição:\n\n"
            msg += "\n".join(f"- {n}" for n in pendentes[:5])
            if len(pendentes) > 5:
                msg += "\n... e outros."
            
            msg += "\n\nPor favor, vá na aba 'Descrições' e selecione o detalhe."
            
            QMessageBox.warning(self, "Seleção Incompleta", msg)
            
            self.tab_widget.setCurrentIndex(1) 
        else:
            self.accept()


class CustomErrorsDialog(QDialog):
    """ Diálogo modal para criar, editar e excluir erros personalizados no catálogo de erros do sistema. """
    def __init__(self, parent=None):
        """ Inicializa o diálogo de gerenciamento de erros personalizados, carrega o catálogo e constrói a interface. """
        super().__init__(parent)
        self.parent_window = parent
        self.errors_file = find_catalog_file("catalogo_erros.json")
        self.custom_errors = self.load_custom_errors()
        
        self.init_ui()
        self.load_existing_errors()

        restore_dialog_position(self, "CustomErrorsDialog/pos")
        
    def init_ui(self):
        """ Constrói a interface com abas para gerenciar nomes de erros e suas descrições detalhadas. """
        self.setWindowTitle("Personalizar Erros")
        self.setFixedSize(700, 600)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QLineEdit, QTextEdit {
                background-color: #3a3a3a;
                border: 2px solid #5a5a5a;
                border-radius: 5px;
                padding: 8px;
                color: white;
                font-size: 12px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 2px solid #0080FF;
            }
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #6a6a6a;
                border-radius: 5px;
                padding: 8px 15px;
                color: white;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            /* ESTILO DOS BOTÕES DE EXCLUIR (VERMELHO) */
            QPushButton#delete_btn {
                background-color: #8B0000;
            }
            QPushButton#delete_btn:hover {
                background-color: #A52A2A;
            }
            QListWidget {
                background-color: #3a3a3a;
                border: 1px solid #5a5a5a;
                border-radius: 5px;
                color: white;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #4a4a4a;
                background-color: transparent;
            }
            QListWidget::item:selected {
                background-color: #0080FF;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #4a4a4a;
            }
            QTabWidget::pane {
                border: 1px solid #5a5a5a;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #4a4a4a;
                color: white;
                padding: 8px 15px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #0080FF;
            }
            QTabBar::tab:hover {
                background-color: #5a5a5a;
            }
            QComboBox {
                background-color: #3a3a3a;
                border: 2px solid #5a5a5a;
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
        """)
        
        main_layout = QVBoxLayout()
        
        title_label = QLabel("Gerenciar Erros Personalizados")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title_label)
        
        self.tab_widget = QTabWidget()
        
        self.create_nome_tab()
        
        self.create_descricao_tab()
        
        main_layout.addWidget(self.tab_widget)
        
        buttons_layout = QHBoxLayout()
        
        save_btn = QPushButton("Salvar Tudo")
        save_btn.clicked.connect(self.save_all_changes)
        buttons_layout.addWidget(save_btn)
        
        main_layout.addLayout(buttons_layout)
        
        self.setLayout(main_layout)
    
    def create_nome_tab(self):
        """ Cria a aba de Nomes de Erro com campo de entrada, lista e botão de exclusão. """
        nome_widget = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Nomes de Erro")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        layout.addWidget(title)
        
        input_layout = QHBoxLayout()
        
        self.nome_input = QLineEdit()
        self.nome_input.setPlaceholderText("Digite um novo nome de erro...")
        input_layout.addWidget(self.nome_input)
        
        add_nome_btn = QPushButton("Adicionar")
        add_nome_btn.clicked.connect(self.add_nome)
        input_layout.addWidget(add_nome_btn)
        
        layout.addLayout(input_layout)
        
        self.nome_list = QListWidget()
        layout.addWidget(self.nome_list)
        
        delete_nome_btn = QPushButton("Excluir Selecionado")
        delete_nome_btn.setObjectName("delete_btn") 
        delete_nome_btn.clicked.connect(self.delete_nome)
        layout.addWidget(delete_nome_btn)
        
        nome_widget.setLayout(layout)
        self.tab_widget.addTab(nome_widget, "Nomes")
    
    def create_descricao_tab(self):
        """ Cria a aba de Descrições com seletor de nome, campo de texto e lista de descrições existentes. """
        descricao_widget = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Descrições")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        layout.addWidget(title)
        
        nome_layout = QHBoxLayout()
        nome_layout.addWidget(QLabel("Nome:"))
        self.combo_nome_desc = QComboBox()
        self.combo_nome_desc.currentTextChanged.connect(self.on_nome_desc_changed)
        nome_layout.addWidget(self.combo_nome_desc)
        layout.addLayout(nome_layout)  

        desc_label = QLabel("Nova Descrição:")
        layout.addWidget(desc_label)
        
        self.descricao_input = QTextEdit()
        self.descricao_input.setPlaceholderText("Digite uma descrição...")
        self.descricao_input.setMaximumHeight(80) 
        layout.addWidget(self.descricao_input)
        
        add_desc_btn = QPushButton("Adicionar Descrição")
        add_desc_btn.clicked.connect(self.add_descricao)
        layout.addWidget(add_desc_btn)
        
        self.descricao_list = QListWidget()
        layout.addWidget(self.descricao_list)
        
        delete_desc_btn = QPushButton("Excluir Selecionado")
        delete_desc_btn.setObjectName("delete_btn") 
        delete_desc_btn.clicked.connect(self.delete_descricao)
        layout.addWidget(delete_desc_btn)
        
        descricao_widget.setLayout(layout)
        self.tab_widget.addTab(descricao_widget, "Descrições")

    def load_custom_errors(self):
        """ Carrega o arquivo catalogo_erros.json ou retorna estrutura vazia se não existir. """
        if os.path.exists(self.errors_file):
            try:
                with open(self.errors_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"nomes": [], "descricoes": {}}
    
    def save_custom_errors(self):
        """ Grava a estrutura de erros personalizada no arquivo catalogo_erros.json em formato JSON. """
        try:
            with open(self.errors_file, 'w', encoding='utf-8') as f:
                json.dump(self.custom_errors, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Erro ao salvar: {e}")
            return False
    
    def load_existing_errors(self):
        """ Popula a lista de nomes com os erros já cadastrados no catálogo. """
        self.nome_list.clear()
        nomes = self.custom_errors.get("nomes", [])
        for nome in nomes:
            self.nome_list.addItem(nome)
        self.update_nome_combo_desc()
    
    def on_nome_desc_changed(self):
        """ Reage à mudança de seleção do combo de nomes e atualiza a lista de descrições. """
        self.update_descricoes_list()
    
    def update_nome_combo_desc(self):
        """ Atualiza a lista de opções do combobox com os nomes de erro disponíveis no catálogo. """
        self.combo_nome_desc.clear()
        self.combo_nome_desc.addItem("Selecione um nome...")
        nomes = self.custom_errors.get("nomes", [])
        for nome in nomes:
            self.combo_nome_desc.addItem(nome)
    
    def update_descricoes_list(self):
        """ Carrega e exibe as descrições associadas ao nome de erro selecionado no combo. """
        self.descricao_list.clear()
        nome_text = self.combo_nome_desc.currentText()
        if nome_text == "Selecione um nome..." or not nome_text:
            return
        
        descricoes = self.custom_errors.get("descricoes", {}).get(nome_text, [])
        for descricao in descricoes:
            display_text = descricao[:50] + "..." if len(descricao) > 50 else descricao
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, descricao)
            self.descricao_list.addItem(item)

    def add_nome(self):
        """ Adiciona um novo nome de erro ao catálogo se não for duplicado. """
        texto = self.nome_input.text().strip()
        if not texto: return
        
        nomes = self.custom_errors.setdefault("nomes", [])
        if texto not in nomes:
            nomes.append(texto)
            self.custom_errors.setdefault("descricoes", {})[texto] = []
            self.nome_list.addItem(texto)
            self.update_nome_combo_desc()
            self.nome_input.clear()

    def add_descricao(self):
        """ Adiciona uma nova descrição ao nome de erro selecionado no combo. """
        nome_text = self.combo_nome_desc.currentText()
        if nome_text == "Selecione um nome..." or not nome_text: return
            
        texto = self.descricao_input.toPlainText().strip()
        if not texto: return
        
        descricoes = self.custom_errors.setdefault("descricoes", {}).setdefault(nome_text, [])
        if texto not in descricoes:
            descricoes.append(texto)
            self.update_descricoes_list()
            self.descricao_input.clear()

    def delete_nome(self):
        """ Remove um nome de erro e todas as suas descrições após confirmação do usuário. """
        current_item = self.nome_list.currentItem()
        if not current_item: return
        
        nome = current_item.text()
        reply = QMessageBox.question(self, 'Confirmar', f"Excluir '{nome}'?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            nomes = self.custom_errors.get("nomes", [])
            if nome in nomes: nomes.remove(nome)
            descricoes = self.custom_errors.get("descricoes", {})
            if nome in descricoes: del descricoes[nome]
            
            self.nome_list.takeItem(self.nome_list.row(current_item))
            self.update_nome_combo_desc()
            self.update_descricoes_list()

    def delete_descricao(self):
        """ Remove uma descrição específica do nome de erro selecionado após confirmação. """
        nome_text = self.combo_nome_desc.currentText()
        current_item = self.descricao_list.currentItem()
        if not current_item or not nome_text or nome_text == "Selecione um nome...": return
        
        descricao_completa = current_item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, 'Confirmar', "Excluir esta descrição?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            descricoes = self.custom_errors.get("descricoes", {}).get(nome_text, [])
            if descricao_completa in descricoes:
                descricoes.remove(descricao_completa)
            self.update_descricoes_list()

    def save_all_changes(self):
        """ Salva todas as alterações no arquivo JSON e fecha o diálogo se bem-sucedido. """
        if self.save_custom_errors():
            QMessageBox.information(self, "Sucesso", "Alterações salvas!")
            self.close()
        else:
            QMessageBox.warning(self, "Erro", "Erro ao salvar!")

    def closeEvent(self, event):
        """ Salva a posição da janela antes de fechar. """
        SETTINGS.setValue("CustomErrorsDialog/pos", self.pos())
        super().closeEvent(event)

    def hideEvent(self, event):
        """ Salva a posição quando a janela é ocultada. """
        SETTINGS.setValue("CustomErrorsDialog/pos", self.pos())
        super().hideEvent(event)

class ClickableLabel(QLabel):
    """ QLabel clicavel usado para transformar logos em atalhos sem alterar o visual. """
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class ManualDialog(QDialog):
    """ Janela interna com um manual rapido do BenIan. """
    def __init__(self, parent, scale_x, scale_y):
        super().__init__(parent)
        self.scale_x = scale_x
        self.scale_y = scale_y

        self.setWindowTitle("Manual do BenIan")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(
            int(610 * self.scale_x),
            int(170 * self.scale_y),
            int(720 * self.scale_x),
            int(700 * self.scale_y)
        )
        self.setMinimumSize(int(560 * self.scale_x), int(520 * self.scale_y))

        self.setStyleSheet(f"""
            QDialog {{
                background-color: #2b2b2b;
                color: white;
            }}
            QTextEdit {{
                background-color: #1f1f1f;
                color: white;
                border: 1px solid #555;
                border-radius: {max(1, int(5 * min(self.scale_x, self.scale_y)))}px;
                padding: {max(6, int(12 * min(self.scale_x, self.scale_y)))}px;
            }}
            QPushButton {{
                background-color: #4a4a4a;
                border: 1px solid #6a6a6a;
                border-radius: {max(1, int(5 * min(self.scale_x, self.scale_y)))}px;
                color: white;
                padding: {max(6, int(10 * min(self.scale_x, self.scale_y)))}px;
                font-size: {max(12, int(15 * min(self.scale_x, self.scale_y)))}px;
            }}
            QPushButton:hover {{
                background-color: #6a6a6a;
            }}
        """)

        text_edit = QTextEdit(self)
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Times", max(12, int(13 * min(scale_x, scale_y)))))

        manual_texto = (
            "<h2 style='text-align: center;'>Manual do BenIan</h2>"
            "<p style='text-align: center;'>"
            "O BenIan é um software de rotulagem e avaliação de imagens biométricas, "
            "pensado para registrar erros observados em cada arquivo analisado."
            "</p><br>"

            "<h3>1. Carregar e navegar</h3>"
            "<ul>"
            "<li><b>Carregar ZIP</b>: selecione um arquivo compactado com as imagens que serão avaliadas.</li>"
            "<li>O programa organiza os arquivos, extrai informações como ID, data, dedo e frame quando disponíveis, e abre a primeira imagem pendente.</li>"
            "<li>Use os botões de navegação, ou as setas esquerda e direita do teclado, para avançar ou voltar nas imagens.</li>"
            "</ul><br>"

            "<h3>2. Visualização da imagem</h3>"
            "<ul>"
            "<li><b>Cores</b>: aplica filtros de visualização, como normal, inverter cores, alto contraste, mais brilhante e mais escuro.</li>"
            "<li><b>Zoom</b>: use a roda do mouse para aproximar ou afastar a imagem. Clique e arraste para mover a visualização ampliada.</li>"
            "<li><b>Camadas RGBA</b>: quando a imagem possuir quatro canais, os botões 1 a 4 permitem visualizar Alpha, cristas, vales e minúcias separadamente.</li>"
            "</ul><br>"

            "<h3>3. Rotulagem de erros</h3>"
            "<ul>"
            "<li><b>Personalizar Erros</b>: cadastre ou edite os nomes de erro e suas descrições no catálogo do sistema.</li>"
            "<li><b>Erro</b>: selecione os erros encontrados na imagem atual e escolha a descrição correspondente.</li>"
            "<li><b>Avaliação</b>: atribua uma nota de 1 a 5 estrelas para cada erro selecionado.</li>"
            "</ul><br>"

            "<h3>4. Salvamento</h3>"
            "<ul>"
            "<li><b>Salvar</b>: grava a anotação da imagem atual no arquivo <code>BENIAN/resultado.json</code>.</li>"
            "<li>Para salvar, é necessário selecionar ao menos um erro e avaliar todos os erros escolhidos.</li>"
            "<li>Após o salvamento, o programa marca o arquivo como avaliado e tenta avançar para a próxima imagem pendente.</li>"
            "</ul><br>"

            "<p style='text-align: center;'>Em caso de dúvidas ou sugestões, entre em contato:</p>"
            "<h3 style='text-align: center;'>matheusaugustooliveira@alunos.utfpr.edu.br</h3>"
        )

        text_edit.setHtml(manual_texto)

        layout = QVBoxLayout(self)
        layout.addWidget(text_edit)

        close_button = QPushButton("Fechar", self)
        close_button.clicked.connect(self.accept)
        close_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(close_button)


class MainWindow(QMainWindow):
    """ Janela principal do aplicativo BenIan para análise e avaliação de imagens biométricas de impressões digitais. """
    def __init__(self):
        """ Inicializa a janela principal, configura escala de resolução, player de áudio e variáveis de estado. """
        super().__init__()
        
        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.screen_height = screen.height()
        
        self.base_width = 1920.0
        self.base_height = 1080.0
        
        self.scale_x = self.screen_width / self.base_width
        self.scale_y = self.screen_height / self.base_height
        
        self.setWindowTitle("BenIan Interface")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint) 
        self.setStyleSheet("QMainWindow { background-color: #2b2b2b; }")

        self.ultimo_estado_avaliacao = None
        self.erros_atuais = []
        self.resultado_file = os.path.join("BENIAN", "resultado.json")
        os.makedirs("BENIAN", exist_ok=True)
        self.current_color_filter = 'normal'
        self.original_pixmap = None
        self.current_file_path = None
        self._rgba_available = False
        self._pending_media_index = None
        self._media_nav_timer = QTimer(self)
        self._media_nav_timer.setSingleShot(True)
        self._media_nav_timer.timeout.connect(self._flush_pending_media_load)
        
        self.init_ui()
        self.showFullScreen()

    def sx(self, val):
        """ Escala um valor horizontal baseado na resolução da tela do usuário. """
        return int(val * self.scale_x)
    
    def sy(self, val):
        """ Escala um valor vertical baseado na resolução da tela do usuário. """
        return int(val * self.scale_y)
    
    def sf(self, size):
        """ Escala um tamanho de fonte ou dimensão mantendo proporção mínima entre escala x e y. """
        return int(size * min(self.scale_x, self.scale_y))

    def init_ui(self):
        """ Constrói toda a interface gráfica incluindo botões, labels, área de visualização e controles. """
        style_btn_large = f"""
            QPushButton {{
                background-color: #4a4a4a;
                border: 1px solid #6a6a6a;
                border-radius: {self.sf(5)}px;
                padding: {self.sf(10)}px;
                color: white;
                font-size: {self.sf(18)}px;
            }}
            QPushButton:hover {{
                background-color: #6a6a6a;  /* Mais claro ao passar o mouse */
                border: 1px solid #8a8a8a;
            }}
            QPushButton:pressed {{
                background-color: #3a3a3a;
                border: 1px solid #4a4a4a;
            }}
        """
        
        style_btn_num = f"""
            QPushButton {{
                background-color: #4a4a4a;
                color: white;
                font-size: {self.sf(18)}px;
                border: 2px solid #6a6a6a;
                border-radius: {self.sf(5)}px;
            }}
            QPushButton:hover {{
                background-color: #6a6a6a; /* Hover nos números também */
            }}
            QPushButton:checked {{
                background-color: #0080FF;
                border-color: #00CCFF;
                font-weight: bold;
            }}
        """

        self.style_field = f"""
            QLabel {{
                background-color: #3a3a3a;
                border: 1px solid #5a5a5a;
                color: white;
                font-size: {self.sf(26)}px; 
                padding: {self.sf(5)}px {self.sf(25)}px; 
            }}
        """
        
        self.style_field_expanded = f"""
            QLabel {{
                background-color: #3a3a3a;
                border: 1px solid #5a5a5a;
                color: white;
                font-size: {self.sf(26)}px;
                padding: {self.sf(5)}px {self.sf(35)}px {self.sf(5)}px {self.sf(35)}px;
            }}
        """

        self.header_widget = QWidget(self)
        self.header_widget.setGeometry(self.sx(320), self.sy(40), self.sx(1280), self.sy(50))
        
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        self.lbl_id = QLabel("ID")
        self.lbl_id.setStyleSheet(self.style_field)
        self.lbl_id.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_id)

        self.lbl_data = QLabel("Data")
        self.lbl_data.setStyleSheet(self.style_field)
        self.lbl_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_data)

        self.lbl_dedo = QLabel("Dedo")
        self.lbl_dedo.setStyleSheet(self.style_field)
        self.lbl_dedo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_dedo)

        self.lbl_frame = QLabel("Frame")
        self.lbl_frame.setStyleSheet(self.style_field)
        self.lbl_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_frame)

        self.lbl_camada = QLabel("4 Camadas RGBA")
        self.lbl_camada.setStyleSheet(self.style_field)
        self.lbl_camada.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_camada)

        self.set_header_mode()
        
        self.header_widget.show()

        video_h_original = 870 
        
        self.video_widget = QWidget(self)
        self.video_widget.setGeometry(self.sx(320), self.sy(100), self.sx(1280), self.sy(video_h_original))
        self.video_widget.setStyleSheet("background-color: black;")

        self.scroll_area = QScrollArea(self.video_widget)
        self.scroll_area.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: black; border: none;")
        
        self.logo_centro = QLabel()
        self.logo_centro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_centro.setStyleSheet("background-color: black;")
        self.logo_centro.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.logo_centro.setMinimumSize(1, 1)
        self.logo_centro.setScaledContents(False)
        self.scroll_area.setWidget(self.logo_centro)
        
        self.zoom_factor = 1.0
        self.current_processed_pixmap = None 

        self.logo_centro.installEventFilter(self)

        self.create_navigation_buttons()
        
        self.load_processed_image(self.logo_centro, "UTFPR_biometria.png", self.sx(380), self.sy(380), opacity=0.3)

        self.btn_carregar = QPushButton("Carregar ZIP", self)
        self.btn_carregar.setGeometry(self.sx(40), self.sy(380), self.sx(200), self.sy(50))
        self.btn_carregar.setStyleSheet(style_btn_large)
        self.btn_carregar.clicked.connect(self.load_zip_file)

        self.btn_cores = QPushButton("Cores", self)
        self.btn_cores.setGeometry(self.sx(40), self.sy(460), self.sx(200), self.sy(50))
        self.btn_cores.setStyleSheet(style_btn_large)
        self.btn_cores.clicked.connect(self.open_color_filters)

        self.btn_personalizar = QPushButton("Personalizar Erros", self)
        self.btn_personalizar.setGeometry(self.sx(40), self.sy(540), self.sx(200), self.sy(50))
        self.btn_personalizar.setStyleSheet(style_btn_large)
        self.btn_personalizar.clicked.connect(self.open_custom_errors)

        self.btn_salvar = QPushButton("Salvar", self)
        self.btn_salvar.setGeometry(self.sx(40), self.sy(620), self.sx(200), self.sy(50))
        self.btn_salvar.setStyleSheet(style_btn_large)
        self.btn_salvar.clicked.connect(self.salvar_anotacao)

        self.btn_num1 = QPushButton("1", self)
        self.btn_num1.setCheckable(True)
        self.btn_num1.setGeometry(self.sx(1660), self.sy(380), self.sx(46), self.sy(50))
        self.btn_num1.setStyleSheet(style_btn_num)
        self.btn_num1.clicked.connect(lambda: self.selecionar_camada(1))

        self.btn_num2 = QPushButton("2", self)
        self.btn_num2.setCheckable(True)
        self.btn_num2.setGeometry(self.sx(1711), self.sy(380), self.sx(46), self.sy(50))
        self.btn_num2.setStyleSheet(style_btn_num)
        self.btn_num2.clicked.connect(lambda: self.selecionar_camada(2))


        self.btn_num3 = QPushButton("3", self)
        self.btn_num3.setCheckable(True)
        self.btn_num3.setGeometry(self.sx(1762), self.sy(380), self.sx(46), self.sy(50))
        self.btn_num3.setStyleSheet(style_btn_num)
        self.btn_num3.clicked.connect(lambda: self.selecionar_camada(3))

        self.btn_num4 = QPushButton("4", self)
        self.btn_num4.setCheckable(True)
        self.btn_num4.setGeometry(self.sx(1813), self.sy(380), self.sx(46), self.sy(50))
        self.btn_num4.setStyleSheet(style_btn_num)
        self.btn_num4.clicked.connect(lambda: self.selecionar_camada(4))

        self.camada_buttons = [self.btn_num1, self.btn_num2, self.btn_num3, self.btn_num4]
        self.camada_atual = None 
        self.canais_rgba = None  

        self.btn_erro = QPushButton("Erro", self)
        self.btn_erro.setGeometry(self.sx(1660), self.sy(460), self.sx(200), self.sy(50))
        self.btn_erro.setStyleSheet(style_btn_large)
        self.btn_erro.clicked.connect(self.open_erro_selector)

        self.btn_avaliacao = QPushButton("Avaliação", self)
        self.btn_avaliacao.setGeometry(self.sx(1660), self.sy(540), self.sx(200), self.sy(50))
        self.btn_avaliacao.setStyleSheet(style_btn_large)
        self.btn_avaliacao.clicked.connect(self.abrir_janela_avaliacao)

        self.lbl_contador = QLabel("0/0", self)
        self.lbl_contador.setGeometry(self.sx(1660), self.sy(620), self.sx(200), self.sy(50))
        self.lbl_contador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_contador.setStyleSheet(f"""
            QLabel {{
                color: white; 
                font-size: {self.sf(18)}px; 
                font-weight: bold;
                background-color: rgba(0, 0, 0, 150);
                border: 2px solid white; 
                border-radius: {self.sf(5)}px;
            }}
        """)

        style_win_ctrl = f"""
            QPushButton {{
                background-color: #4a4a4a;
                border: 1px solid #6a6a6a;
                border-radius: {self.sf(5)}px;
                padding: {self.sf(5)}px;
            }}
            QPushButton:hover {{
                background-color: #5a5a5a;
            }}
            QPushButton:pressed {{
                background-color: #3a3a3a;
            }}
        """
        
        style_close = f"""
            QPushButton {{
                background-color: #4a4a4a;
                border: 1px solid #6a6a6a;
                border-radius: {self.sf(5)}px;
                padding: {self.sf(5)}px;
            }}
            QPushButton:hover {{
                background-color: #ff4444;
            }}
            QPushButton:pressed {{
                background-color: #dd3333;
            }}
        """

        self.btn_minimizar = QPushButton(self)
        self.btn_minimizar.setIcon(self.create_icon(QStyle.StandardPixmap.SP_TitleBarMinButton))
        self.btn_minimizar.setGeometry(self.sx(1710), self.sy(10), self.sx(60), self.sy(30))
        self.btn_minimizar.setStyleSheet(style_win_ctrl)
        self.btn_minimizar.setToolTip("Minimizar")
        self.btn_minimizar.clicked.connect(self.showMinimized)

        self.btn_restaurar = QPushButton(self)
        self.btn_restaurar.setIcon(self.create_icon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.btn_restaurar.setGeometry(self.sx(1780), self.sy(10), self.sx(60), self.sy(30))
        self.btn_restaurar.setStyleSheet(style_win_ctrl)
        self.btn_restaurar.setToolTip("Restaurar visualização")
        self.btn_restaurar.clicked.connect(self.reset_zoom)

        self.btn_fechar = QPushButton(self)
        self.btn_fechar.setIcon(self.create_icon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.btn_fechar.setGeometry(self.sx(1850), self.sy(10), self.sx(60), self.sy(30))
        self.btn_fechar.setStyleSheet(style_close)
        self.btn_fechar.clicked.connect(self.close)

        self.logo_cnpq = ClickableLabel(self)
        self.logo_cnpq.setGeometry(self.sx(40), self.sy(905), self.sx(190), self.sy(65))
        self.load_processed_image(self.logo_cnpq, "CNPQ.png", self.sx(190), self.sy(65), opacity=1.0)
        self.logo_cnpq.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_cnpq.setToolTip("Abrir manual do BenIan")
        self.logo_cnpq.clicked.connect(self.open_manual)
        
        self.logo_utfpr = ClickableLabel(self)
        self.logo_utfpr.setGeometry(self.sx(1663), self.sy(905), self.sx(190), self.sy(65))
        self.load_processed_image(self.logo_utfpr, "UTFPR.png", self.sx(190), self.sy(65), opacity=1.0)
        self.logo_utfpr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_utfpr.setToolTip("Abrir site do projeto")
        self.logo_utfpr.clicked.connect(self.open_project_site)

    def create_icon(self, standard_pixmap):
        """ Cria um ícone branco estilizado a partir de um ícone padrão do sistema. """
        icon = self.style().standardIcon(standard_pixmap)
        pix = icon.pixmap(self.sf(16), self.sf(16))
        mask = pix.mask()
        pix.fill(QColor("white"))
        pix.setMask(mask)
        return QIcon(pix)

    def load_processed_image(self, label, filename, w, h, opacity=1.0):
        """ Carrega a imagem e aplica o efeito de silhueta branca + opacidade, idêntico ao código original do BenIan.py """
        path = resource_path(os.path.join("Fotos", filename))
        
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                
                white_pixmap = QPixmap(scaled.size())
                white_pixmap.fill(Qt.GlobalColor.transparent)
                
                painter = QPainter(white_pixmap)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                painter.drawPixmap(0, 0, scaled)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(white_pixmap.rect(), Qt.GlobalColor.white)
                painter.end()
                
                final_pixmap = white_pixmap
                if opacity < 1.0:
                    transparent_pixmap = QPixmap(white_pixmap.size())
                    transparent_pixmap.fill(Qt.GlobalColor.transparent)
                    
                    painter2 = QPainter(transparent_pixmap)
                    painter2.setOpacity(opacity)
                    painter2.drawPixmap(0, 0, white_pixmap)
                    painter2.end()
                    final_pixmap = transparent_pixmap
                
                label.setPixmap(final_pixmap)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if label is getattr(self, 'logo_centro', None):
                    label.resize(final_pixmap.size())
                return
        
        label.setText(filename.replace(".png", ""))
        label.setStyleSheet("color: rgba(255,255,255,100); font-weight: bold; border: 1px dashed #555;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def toggle_maximize(self):
        """ Alterna entre modo tela cheia e janela normal. """
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    def open_manual(self):
        """ Abre ou foca o manual interno do BenIan. """
        if hasattr(self, 'manual_dialog') and self.manual_dialog and self.manual_dialog.isVisible():
            self.manual_dialog.raise_()
            self.manual_dialog.activateWindow()
            return

        self.manual_dialog = ManualDialog(self, self.scale_x, self.scale_y)
        self.manual_dialog.show()

    def open_project_site(self):
        """ Abre o site do projeto de biometria da UTFPR no navegador padrao. """
        QDesktopServices.openUrl(QUrl("https://sites.google.com/view/utfprbiometria"))

    def open_custom_errors(self):
        """ Abre o diálogo de personalização de erros para criar e editar o catálogo. """
        dialog = CustomErrorsDialog(self)
        dialog.exec()

    def _erro_key(self, erro):
        return (erro.get('nome'), erro.get('descricao'))

    def _avaliacoes_por_erro(self):
        avaliacoes = {}

        for erro in self.erros_atuais:
            avaliacao = erro.get('avaliacao')
            if avaliacao:
                avaliacoes[self._erro_key(erro)] = avaliacao

        if self.ultimo_estado_avaliacao:
            for erro_index, avaliacao in self.ultimo_estado_avaliacao.items():
                try:
                    idx = int(erro_index)
                except (TypeError, ValueError):
                    continue
                if avaliacao and 0 <= idx < len(self.erros_atuais):
                    avaliacoes[self._erro_key(self.erros_atuais[idx])] = avaliacao

        dialog = getattr(self, 'avaliacao_dialog', None)
        if dialog:
            erros_dialog = getattr(dialog, 'erros_selecionados', [])
            for erro_index, avaliacao in dialog.get_avaliacoes().items():
                try:
                    idx = int(erro_index)
                except (TypeError, ValueError):
                    continue
                if avaliacao and 0 <= idx < len(erros_dialog):
                    avaliacoes[self._erro_key(erros_dialog[idx])] = avaliacao

        return avaliacoes

    def _salvar_estado_avaliacao_atual_por_indice(self):
        estado = {
            i: erro.get('avaliacao')
            for i, erro in enumerate(self.erros_atuais)
            if erro.get('avaliacao')
        }
        self.ultimo_estado_avaliacao = estado or None

    def open_erro_selector(self):
        """ Abre o diálogo de seleção de erros e processa a escolha do usuário. """
        if not self.verificar_zip_carregado():
            return

        if hasattr(self, 'erro_dialog') and self.erro_dialog and self.erro_dialog.isVisible():
            self.erro_dialog.raise_()
            self.erro_dialog.activateWindow()
            return
        
        custom_errors = {}
        path_json = find_catalog_file("catalogo_erros.json")
        if os.path.exists(path_json):
             try:
                 with open(path_json, 'r', encoding='utf-8') as f:
                     custom_errors = json.load(f)
             except:
                 pass

        self.erro_dialog = ErroDialog(self, custom_errors)
        # Sincroniza o estado de erros mesmo ao fechar/cancelar, evitando avaliação com seleção antiga.
        self.erro_dialog.finished.connect(lambda _: self.processar_selecao_erros(self.erro_dialog))
        self.erro_dialog.show()

    def processar_selecao_erros(self, dialog):
        """ Processa os erros selecionados após o usuário confirmar a seleção. """
        if dialog is None:
            return

        _, descricoes = dialog.get_selections()

        avaliacoes_por_erro = self._avaliacoes_por_erro()
        erros_novos = []
        for nome, desc in descricoes:
            erro = {"nome": nome, "descricao": desc}
            avaliacao = avaliacoes_por_erro.get((nome, desc))
            if avaliacao:
                erro['avaliacao'] = avaliacao
            erros_novos.append(erro)

        assinatura_anterior = [(e.get('nome'), e.get('descricao')) for e in self.erros_atuais]
        assinatura_nova = [(e['nome'], e['descricao']) for e in erros_novos]

        if assinatura_nova != assinatura_anterior:
            if hasattr(self, 'avaliacao_dialog') and self.avaliacao_dialog and self.avaliacao_dialog.isVisible():
                self.avaliacao_dialog.close()

        self.erros_atuais = erros_novos
        self._salvar_estado_avaliacao_atual_por_indice()

    def create_icon(self, standard_pixmap):
        """ Cria um ícone colorido com alta qualidade (igual ao BenIan.py) """
        icon = self.style().standardIcon(standard_pixmap)
        size = self.sf(16) 
        pixmap = icon.pixmap(size, size)
        
        colored_pixmap = QPixmap(size, size)
        colored_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(colored_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(colored_pixmap.rect(), QColor("white"))
        painter.end()
        
        return QIcon(colored_pixmap)

    def abrir_janela_avaliacao(self):
        """ Abre a janela de avaliação dos erros selecionados com sistema de estrelas. """
        if not self.verificar_zip_carregado():
            return
        
        if not self.erros_atuais:
            QMessageBox.warning(self, "Atenção", "Nenhum erro selecionado! Selecione erros primeiro.")
            return

        if hasattr(self, 'avaliacao_dialog') and self.avaliacao_dialog and self.avaliacao_dialog.isVisible():
            self.avaliacao_dialog.raise_()
            self.avaliacao_dialog.activateWindow()
            return
        
        self.avaliacao_dialog = AvaliacaoDialog(self, self.erros_atuais)
        
        if self.ultimo_estado_avaliacao:
            self.avaliacao_dialog.restaurar_avaliacoes(self.ultimo_estado_avaliacao)
        
        self.avaliacao_dialog.finished.connect(self.salvar_estado_avaliacao)
        self.avaliacao_dialog.accepted.connect(self.processar_avaliacoes)
        
        self.avaliacao_dialog.show()

    def salvar_estado_avaliacao(self):
        """ Persiste temporariamente o estado das avaliações quando a janela de avaliação fecha. """
        if hasattr(self, 'avaliacao_dialog') and self.avaliacao_dialog:
            self.ultimo_estado_avaliacao = self.avaliacao_dialog.get_avaliacoes()

    def processar_avaliacoes(self):
        """ Valida se todas as avaliações estão completas e integra as notas aos erros atuais. """
        if not hasattr(self, 'avaliacao_dialog') or not self.avaliacao_dialog:
            return

        if not self.avaliacao_dialog.todas_avaliacoes_preenchidas(): 
            QMessageBox.warning(self, "Incompleto", "Por favor, avalie todos os erros antes de confirmar!")
            QTimer.singleShot(100, self.avaliacao_dialog.show)
            return

        notas = self.avaliacao_dialog.get_avaliacoes()
        for i, erro in enumerate(self.erros_atuais):
            if i in notas:
                erro['avaliacao'] = notas[i]
        
        self.ultimo_estado_avaliacao = None
        

    def load_zip_file(self):
        """ Abre seletor de arquivo ZIP e inicia thread de extração em segundo plano. """
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecionar Arquivo ZIP", "", "Arquivos ZIP (*.zip)")
        if not file_path:
            return

        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            try: shutil.rmtree(self.temp_dir)
            except: pass

        self.temp_dir = tempfile.mkdtemp()
        self.current_zip_name = os.path.basename(file_path)
        self.media_files = []
        self.current_media_index = 0
        self._pending_media_index = None
        self._media_nav_timer.stop()

        self.progress_dialog = ProgressDialog(self)
        self.zip_thread = ZipLoaderThread(file_path, self.temp_dir)
        
        self.zip_thread.progress.connect(self.progress_dialog.update_progress)
        self.zip_thread.finished.connect(self.on_zip_finished)
        self.zip_thread.error.connect(lambda err: QMessageBox.critical(self, "Erro", str(err)))
        
        self.progress_dialog.show()
        self.zip_thread.start()

    def on_zip_finished(self, media_files):
        """ Processa a lista de arquivos extraídos e posiciona na primeira imagem não avaliada. """
        if not media_files:
            QMessageBox.warning(self, "Aviso", "Nenhuma imagem encontrada.")
            return
            
        self.media_files = media_files
        
        self.load_progress_data()
        
        first_unevaluated_index = 0
        for i, item in enumerate(self.media_files):
            if item['filename'] not in self.evaluated_files:
                first_unevaluated_index = i
                break
        
        if len(self.evaluated_files) == len(self.media_files) and len(self.media_files) > 0:
            first_unevaluated_index = 0
            
        self.current_media_index = first_unevaluated_index
        
        self.request_media_load(self.current_media_index, immediate=True)
        
        total = len(self.media_files)
        avaliados = len(self.evaluated_files)
        pendentes = total - avaliados
        
        QTimer.singleShot(100, lambda: QMessageBox.information(
            self, 
            "ZIP Carregado", 
            f"Total: {total} arquivos\n"
            f"Avaliados: {avaliados}\n"
            f"Pendentes: {pendentes}"
        ))

    def request_media_load(self, target_index, immediate=False):
        """ Agenda o carregamento da imagem atual com debounce para evitar sobrecarga em navegaÃ§Ã£o rÃ¡pida. """
        if not hasattr(self, 'media_files') or not self.media_files:
            return

        target_index = max(0, min(target_index, len(self.media_files) - 1))
        self.current_media_index = target_index
        self._pending_media_index = target_index
        if immediate:
            self._media_nav_timer.start(0)
            return

        if not self._media_nav_timer.isActive():
            self._media_nav_timer.start(15)

    def _flush_pending_media_load(self):
        """ Executa o Ãºltimo carregamento pendente de imagem solicitado pela navegaÃ§Ã£o. """
        if self._pending_media_index is None:
            return
        if not hasattr(self, 'media_files') or not self.media_files:
            self._pending_media_index = None
            return

        self.current_media_index = self._pending_media_index
        self._pending_media_index = None
        self.load_current_media()

    def load_current_media(self):
        """ Carrega a imagem atual, detecta camadas RGBA, atualiza interface e prepara visualização. """
        if not self.media_files:
            return

        item = self.media_files[self.current_media_index]
        file_path = item['file_path'] 
        self.current_file_path = file_path
        
        self.lbl_id.setText(str(item['id']).upper())
        self.lbl_data.setText(str(item['data']))
        self.lbl_dedo.setText(str(item['dedo']))
        self.lbl_frame.setText(f"Frame: {item.get('frame', 0)}")
        self.set_data_mode()
        
        self.camada_atual = None
        self.canais_rgba = None
        self._rgba_available = False
        for btn in self.camada_buttons:
            btn.setChecked(False)
            btn.setEnabled(False) 

        img_cv = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)

        if img_cv is not None and img_cv.ndim == 3 and img_cv.shape[2] == 4:
            self.lbl_camada.setText("4 Camadas")
            self._rgba_available = True
            
            for btn in self.camada_buttons:
                btn.setEnabled(True)
            
        else:
            self.lbl_camada.setText("Imagem Normal")

        pixmap = QPixmap(file_path)
        self.original_pixmap = pixmap
        self.master_pixmap = pixmap
        
        if self.original_pixmap.isNull():
            self.logo_centro.setText("Erro ao carregar")
            return

        self.apply_image_filter(self.current_color_filter)
        self.update_contador_ui()
        
        self.controls_bg.show()
        self.btn_prev_img.show()
        self.btn_next_img.show()
        self.controls_bg.raise_()
        self.btn_prev_img.raise_()
        self.btn_next_img.raise_()         

    def update_contador_ui(self):
        """ Atualiza o contador de navegação e altera sua cor conforme status de avaliação. """
        if hasattr(self, 'media_files') and self.media_files:
            self.lbl_contador.setText(f"{self.current_media_index + 1}/{len(self.media_files)}")
        else:
            self.lbl_contador.setText("0/0")
    
    def next_image(self):
        """ Avança para a próxima imagem na lista de mídias carregadas. """
        if hasattr(self, 'media_files') and self.media_files:
            if self.current_media_index < len(self.media_files) - 1:
                self.request_media_load(self.current_media_index + 1)

    def prev_image(self):
        """ Retorna para a imagem anterior na lista de mídias carregadas. """
        if hasattr(self, 'media_files') and self.media_files:
            if self.current_media_index > 0:
                self.request_media_load(self.current_media_index - 1)
    
    def keyPressEvent(self, event):
        """ Captura eventos de teclado para navegação e controle da interface. """
        if event.key() == Qt.Key.Key_Right:
            self.next_image()
        elif event.key() == Qt.Key.Key_Left:
            self.prev_image()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)
    
    def create_navigation_buttons(self):
        """ Cria os botões circulares de navegação anterior/próximo abaixo da área de visualização. """
        v_geo = self.video_widget.geometry()
        
        bar_y = v_geo.y() + v_geo.height()
        bar_h = self.sy(80) 
        bar_w = v_geo.width()
        bar_x = v_geo.x()

        self.controls_bg = QLabel(self)
        self.controls_bg.setGeometry(bar_x, bar_y, bar_w, bar_h)
        self.controls_bg.setStyleSheet("""
            background-color: #1e1e1e; 
            border-bottom-left-radius: 5px; 
            border-bottom-right-radius: 5px;
            border-top: 2px solid #3a3a3a;
        """)
        self.controls_bg.hide() 

        btn_size = self.sf(50)
        radius = btn_size // 2
        
        btn_y = bar_y + (bar_h - btn_size) // 2
        
        center_x = bar_x + (bar_w // 2)
        spacing = self.sx(20)

        circle_style = f"""
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555;
                border-radius: {radius}px;
            }}
            QPushButton:hover {{
                background-color: #444;
                border: 1px solid white;
            }}
            QPushButton:pressed {{
                background-color: #0080FF;
            }}
        """

        self.btn_prev_img = QPushButton(self)
        self.btn_prev_img.setIcon(self.create_icon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.btn_prev_img.setIconSize(QSize(self.sf(24), self.sf(24)))
        self.btn_prev_img.setGeometry(center_x - spacing - btn_size, btn_y, btn_size, btn_size)
        self.btn_prev_img.setStyleSheet(circle_style)
        self.btn_prev_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev_img.clicked.connect(self.prev_image)
        self.btn_prev_img.hide()

        self.btn_next_img = QPushButton(self)
        self.btn_next_img.setIcon(self.create_icon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self.btn_next_img.setIconSize(QSize(self.sf(24), self.sf(24)))
        self.btn_next_img.setGeometry(center_x + spacing, btn_y, btn_size, btn_size)
        self.btn_next_img.setStyleSheet(circle_style)
        self.btn_next_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_img.clicked.connect(self.next_image)
        self.btn_next_img.hide()

    def load_progress_data(self):
        """ Carrega do resultado.json quais arquivos já foram avaliados para o ZIP atual. """
        self.evaluated_files = set()
        
        data = self.load_resultado_json()
        
        if self.current_zip_name in data:
            lista_entradas = data[self.current_zip_name]
            for entrada in lista_entradas:
                self.evaluated_files.add(entrada['arquivo'])

    def save_current_as_evaluated(self):
        """ Marca a imagem atual como avaliada e pula automaticamente para a próxima pendente. """
        if not self.media_files: return

        current_file = self.media_files[self.current_media_index]['filename']
        self.evaluated_files.add(current_file)
        
        full_data = {}
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    full_data = json.load(f)
            except: pass
        
        full_data[self.current_zip_name] = list(self.evaluated_files)
        
        with open(self.progress_file, 'w') as f:
            json.dump(full_data, f)
            
        self.update_contador_ui()
        
        self.jump_to_next_unevaluated()

    def jump_to_next_unevaluated(self):
        """ Procura e carrega a próxima imagem que ainda não foi avaliada. """
        start_index = self.current_media_index + 1
        
        for i in range(start_index, len(self.media_files)):
            if self.media_files[i]['filename'] not in self.evaluated_files:
                self.current_media_index = i
                self.request_media_load(self.current_media_index, immediate=True)
                return

        QMessageBox.information(self, "Concluído", "Você chegou ao fim da lista ou todas as imagens seguintes já foram avaliadas!")

    def update_contador_ui(self):
        """ Atualiza o texto e a cor do contador (Vermelho=Pendente, Verde=Feito). """
        if not hasattr(self, 'media_files') or not self.media_files:
            self.lbl_contador.setText("0/0")
            return

        current_file = self.media_files[self.current_media_index]['filename']
        is_evaluated = current_file in self.evaluated_files
        
        color = "#00FF00" if is_evaluated else "#FF0000" 
        bg_color = "rgba(0, 50, 0, 150)" if is_evaluated else "rgba(50, 0, 0, 150)"
        
        self.lbl_contador.setText(f"{self.current_media_index + 1}/{len(self.media_files)}")
        self.lbl_contador.setStyleSheet(f"""
            QLabel {{
                color: {color}; 
                font-size: {self.sf(18)}px; 
                font-weight: bold;
                background-color: {bg_color};
                border: 2px solid {color}; 
                border-radius: {self.sf(5)}px;
            }}
        """)
    
    def get_current_timestamp(self):
        """ Retorna o timestamp atual formatado para registro de avaliações. """
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_resultado_json(self):
        """ Carrega a estrutura completa do arquivo resultado.json ou retorna dicionário vazio. """
        if os.path.exists(self.resultado_file):
            try:
                with open(self.resultado_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Erro ao ler JSON: {e}")
        return {}

    def save_resultado_json(self, data):
        """ Persiste a estrutura de dados de resultados no arquivo resultado.json. """
        try:
            with open(self.resultado_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Erro ao salvar JSON: {e}")
            return False
    
    def salvar_anotacao(self):
        """ Valida e salva a avaliação completa da imagem atual no resultado.json. """
        if not self.verificar_zip_carregado():
            return
        
        if not hasattr(self, 'current_zip_name') or not self.current_zip_name:
            QMessageBox.warning(self, "Erro", "Nenhum ZIP carregado!")
            return
        
        if not self.media_files or self.current_media_index >= len(self.media_files):
            QMessageBox.warning(self, "Erro", "Nenhuma mídia selecionada!")
            return
            
        if not self.erros_atuais:
            QMessageBox.warning(self, "Atenção", "Nenhum erro foi selecionado! Use o botão 'Erro' primeiro.")
            return
            
        erros_sem_avaliacao = [e['nome'] for e in self.erros_atuais if not e.get('avaliacao')]
        if erros_sem_avaliacao:
            msg = f"Avalie todos os erros antes de salvar!\nPendentes: {', '.join(erros_sem_avaliacao)}"
            QMessageBox.warning(self, "Incompleto", msg)
            return

        item = self.media_files[self.current_media_index]
        
        arquivo_para_salvar = item['filename']
        
        if item.get('type') == 'layered_video':
            layers = item.get('layers', {})
            first_layer = next(iter(layers.values())) if layers else None
            ext = os.path.splitext(first_layer['filename'])[1] if first_layer else ""
            arquivo_para_salvar = f"{item['base_name']}{ext}"

        resultado_data = self.load_resultado_json()
        
        if self.current_zip_name not in resultado_data:
            resultado_data[self.current_zip_name] = []
            
        entrada_existente = None
        for entrada in resultado_data[self.current_zip_name]:
            if entrada['arquivo'] == arquivo_para_salvar:
                entrada_existente = entrada
                break
        
        if not entrada_existente:
            entrada_existente = {
                "arquivo": arquivo_para_salvar,
                "data": item['data'],
                "id": item['id'],
                "dedo": item['dedo'],
                "erros": []
            }
            resultado_data[self.current_zip_name].append(entrada_existente)
            
        camada_info = ""
            
        for erro in self.erros_atuais:
            novo_erro = {
                "nome": erro['nome'],
                "descricao": erro['descricao'],
                "avaliacao": erro['avaliacao'],
                "timestamp": self.get_current_timestamp()
            }
            
            duplicado = any(
                e['nome'] == novo_erro['nome'] and 
                e['descricao'] == novo_erro['descricao'] 
                for e in entrada_existente['erros']
            )
            
            if not duplicado:
                entrada_existente['erros'].append(novo_erro)

        if self.save_resultado_json(resultado_data):
            
            camada_info = ""
            if self.camada_atual:
                nomes_camadas = {
                    1: "Calibrado (Alpha)",
                    2: "Segmentação Cristas (R)", 
                    3: "Segmentação Vales (G)", 
                    4: "Minúcias (B)"
                }
                nome_extenso = nomes_camadas.get(self.camada_atual, f"Camada {self.camada_atual}")
                camada_info = f" ({nome_extenso})"

            qtd_erros = len(self.erros_atuais)
            
            mensagem_final = (
                f"Avaliação salva com sucesso!\n"
                f"Arquivo: {arquivo_para_salvar}{camada_info}\n"
                f"Erros: {qtd_erros}"
            )
            
            QMessageBox.information(self, "Sucesso", mensagem_final)

            self.evaluated_files.add(item['filename']) 

            self.limpar_formulario()
            
            self.update_contador_ui()
            self.jump_to_next_unevaluated()
            
        else:
            QMessageBox.critical(self, "Erro Crítico", "Falha ao gravar no arquivo resultado.json")

    def limpar_formulario(self):
        """ Reseta o estado de erros e avaliações após salvar com sucesso. """
        if hasattr(self, 'erro_dialog') and self.erro_dialog:
            dialog = self.erro_dialog
            try:
                if hasattr(dialog, 'clear_all_selections'):
                    dialog.clear_all_selections()
                if hasattr(dialog, 'salvar_selecao_atual'):
                    dialog.salvar_selecao_atual()
                dialog.finished.disconnect()
            except TypeError:
                pass
            finally:
                dialog.blockSignals(True)
                dialog.close()
                dialog.blockSignals(False)
                self.erro_dialog = None

        if hasattr(self, 'avaliacao_dialog') and self.avaliacao_dialog:
            dialog = self.avaliacao_dialog
            try:
                dialog.finished.disconnect()
                dialog.accepted.disconnect()
            except TypeError:
                pass
            finally:
                dialog.blockSignals(True)
                dialog.close()
                dialog.blockSignals(False)
                self.avaliacao_dialog = None

        SETTINGS.remove("ErroDialog/selected_names")
        SETTINGS.remove("ErroDialog/selected_descriptions")
        SETTINGS.sync()

        self.erros_atuais = []
        self.ultimo_estado_avaliacao = None
    
    def open_color_filters(self):
        """ Abre ou foca a janela de filtros de cor mantendo o filtro atual selecionado. """
        if not self.verificar_zip_carregado():
            return
        
        if hasattr(self, 'color_dialog') and self.color_dialog and self.color_dialog.isVisible():
            self.color_dialog.raise_()
            self.color_dialog.activateWindow()
            return

        self.color_dialog = ColorFiltersDialog(self)
        self.color_dialog.restore_current_filter(self.current_color_filter)
        self.color_dialog.show()

    def apply_image_filter(self, filter_type):
        """ Aplica o filtro de processamento de imagem selecionado e atualiza a visualização. """
        if not hasattr(self, 'original_pixmap') or not self.original_pixmap:
            return
        
        self.current_color_filter = filter_type
        processed_pixmap = None

        if filter_type == 'normal':
            processed_pixmap = self.original_pixmap
            
        elif filter_type == 'invert':
            image = self.original_pixmap.toImage()
            image.invertPixels()
            processed_pixmap = QPixmap.fromImage(image)
            
        elif filter_type == 'bright':
            processed_pixmap = QPixmap(self.original_pixmap.size())
            processed_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(processed_pixmap)
            painter.drawPixmap(0, 0, self.original_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            painter.setOpacity(0.3)
            painter.fillRect(processed_pixmap.rect(), Qt.GlobalColor.white)
            painter.end()
            
        elif filter_type == 'dark':
            processed_pixmap = QPixmap(self.original_pixmap.size())
            processed_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(processed_pixmap)
            painter.drawPixmap(0, 0, self.original_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            painter.setOpacity(0.4)
            painter.fillRect(processed_pixmap.rect(), Qt.GlobalColor.black)
            painter.end()
            
        elif filter_type == 'high_contrast':
            processed_pixmap = QPixmap(self.original_pixmap.size())
            processed_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(processed_pixmap)
            painter.drawPixmap(0, 0, self.original_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
            painter.setOpacity(0.6)
            painter.drawPixmap(0, 0, self.original_pixmap)
            painter.end()
        
        else:
            processed_pixmap = self.original_pixmap

        self.current_processed_pixmap = processed_pixmap
        
        self._update_image_display()

    def _update_image_display(self, smooth=True):
        """ Renderiza a imagem processada com o fator de zoom aplicado na área de visualização. """
        if not self.current_processed_pixmap:
            return

        view_w = max(1, self.video_widget.width())
        view_h = max(1, self.video_widget.height())
        
        orig_w = self.current_processed_pixmap.width()
        orig_h = self.current_processed_pixmap.height()
        if orig_w <= 0 or orig_h <= 0:
            return

        fit_ratio = min(view_w / orig_w, view_h / orig_h)
        base_w = max(1, int(orig_w * fit_ratio))
        base_h = max(1, int(orig_h * fit_ratio))
        
        final_w = max(1, int(base_w * self.zoom_factor))
        final_h = max(1, int(base_h * self.zoom_factor))
        
        final_pix = self.current_processed_pixmap.scaled(
            final_w, final_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation
        )
        
        self.logo_centro.setUpdatesEnabled(False)
        self.logo_centro.setPixmap(final_pix)
        self.logo_centro.resize(final_pix.size())
        self.logo_centro.setUpdatesEnabled(True)
        self.logo_centro.update()
    
    def selecionar_camada(self, numero):
        """ Alterna a visualização entre camadas RGBA individuais ou imagem original completa. """
        if not self.verificar_zip_carregado():
            
            if hasattr(self, 'camada_buttons') and 0 <= numero-1 < len(self.camada_buttons):
                btn = self.camada_buttons[numero-1]
                
                btn.blockSignals(True)
                btn.setChecked(False)  
                btn.blockSignals(False)
            
            return

        if not self._rgba_available:
            return

        if self.canais_rgba is None:
            if not self.current_file_path:
                return

            img_cv = cv2.imread(self.current_file_path, cv2.IMREAD_UNCHANGED)
            if img_cv is None or img_cv.ndim != 3 or img_cv.shape[2] != 4:
                self._rgba_available = False
                self.lbl_camada.setText("Imagem Normal")
                for btn in self.camada_buttons:
                    btn.setChecked(False)
                    btn.setEnabled(False)
                return

            b, g, r, a = cv2.split(img_cv)
            self.canais_rgba = [a, r, g, b]

        if self.camada_atual == numero:
            self.camada_atual = None
            self.camada_buttons[numero-1].setChecked(False)
    
            self.original_pixmap = self.master_pixmap
            self.lbl_camada.setText("Original")
            self.apply_image_filter(self.current_color_filter)
            return

        self.camada_atual = numero
        
        for i, btn in enumerate(self.camada_buttons):
            btn.blockSignals(True)
            btn.setChecked((i + 1) == numero)
            btn.blockSignals(False)

        canal = self.canais_rgba[numero - 1]
        
        nomes_camadas = {
            1: "Calibrado (Alpha)",
            2: "Segmentação Cristas (R)", 
            3: "Segmentação Vales (G)", 
            4: "Minúcias (B)"
        }
        self.lbl_camada.setText(nomes_camadas.get(numero, f"Camada {numero}"))

        height, width = canal.shape
        bytes_per_line = width
        
        q_img = QImage(canal.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        
        pixmap_camada = QPixmap.fromImage(q_img)
        
        self.original_pixmap = pixmap_camada
        self.apply_image_filter(self.current_color_filter)
    
    def eventFilter(self, source, event):
        """ Intercepta eventos do mouse para implementar pan (arrastar) e zoom com scroll. """
        if source is self.logo_centro and self.original_pixmap:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._pan_active = True
                self._pan_start = event.globalPosition().toPoint()
                self._h0 = self.scroll_area.horizontalScrollBar().value()
                self._v0 = self.scroll_area.verticalScrollBar().value()
                self.logo_centro.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True

            if event.type() == QEvent.Type.MouseMove and getattr(self, '_pan_active', False):
                delta = event.globalPosition().toPoint() - self._pan_start
                self.scroll_area.horizontalScrollBar().setValue(self._h0 - delta.x())
                self.scroll_area.verticalScrollBar().setValue(self._v0 - delta.y())
                return True

            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._pan_active = False
                self.logo_centro.setCursor(Qt.CursorShape.ArrowCursor)
                return True

            if event.type() == QEvent.Type.Wheel:
                if not self.current_processed_pixmap:
                    return False

                pos = event.position().toPoint()
                viewport_pos = self.logo_centro.mapTo(self.scroll_area.viewport(), pos)
                hbar = self.scroll_area.horizontalScrollBar()
                vbar = self.scroll_area.verticalScrollBar()

                w0 = self.logo_centro.width()
                h0 = self.logo_centro.height()
                if w0 == 0 or h0 == 0: return False

                delta = event.angleDelta().y()
                factor = 1.10 if delta > 0 else 0.90
                
                new_zoom = self.zoom_factor * factor
                if new_zoom < 0.1 or new_zoom > 20.0:
                    return True

                self.zoom_factor = new_zoom
                
                self._update_image_display(smooth=False)

                w1 = self.logo_centro.width()
                h1 = self.logo_centro.height()
                
                new_scroll_h = int(pos.x() * (w1 / w0) - viewport_pos.x())
                new_scroll_v = int(pos.y() * (h1 / h0) - viewport_pos.y())
                
                hbar.setValue(new_scroll_h)
                vbar.setValue(new_scroll_v)

                return True

        return super().eventFilter(source, event)

    def reset_zoom(self):
        """ Restaura zoom e visualização padrão (imagem completa sem filtro/camada). """
        self.zoom_factor = 1.0

        for btn in self.camada_buttons:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)

        self.camada_atual = None
        self.current_color_filter = 'normal'

        if hasattr(self, 'master_pixmap') and self.master_pixmap:
            self.original_pixmap = self.master_pixmap

        self.lbl_camada.setText("4 Camadas" if self._rgba_available else "Imagem Normal")
        self.apply_image_filter('normal')

        if hasattr(self, 'color_dialog') and self.color_dialog and self.color_dialog.isVisible():
            self.color_dialog.restore_current_filter('normal')
    
    def set_header_mode(self):
        """ Configura o cabeçalho no modo inicial onde todos os campos expandem igualmente. """
        policy = QSizePolicy.Policy.Expanding
        
        self.lbl_id.setSizePolicy(policy, QSizePolicy.Policy.Preferred)
        self.lbl_data.setSizePolicy(policy, QSizePolicy.Policy.Preferred)
        self.lbl_dedo.setSizePolicy(policy, QSizePolicy.Policy.Preferred)
        self.lbl_frame.setSizePolicy(policy, QSizePolicy.Policy.Preferred)
        self.lbl_camada.setSizePolicy(policy, QSizePolicy.Policy.Preferred)
        
        self.lbl_dedo.setStyleSheet(self.style_field)
        self.lbl_camada.setStyleSheet(self.style_field)

    def set_data_mode(self):
        """ Configura o cabeçalho no modo de dados onde Dedo e Camada expandem mais. """
        min_policy = QSizePolicy.Policy.Minimum
        exp_policy = QSizePolicy.Policy.Expanding
        
        self.lbl_id.setSizePolicy(min_policy, QSizePolicy.Policy.Preferred)
        self.lbl_data.setSizePolicy(min_policy, QSizePolicy.Policy.Preferred)
        self.lbl_frame.setSizePolicy(min_policy, QSizePolicy.Policy.Preferred)
        
        self.lbl_dedo.setSizePolicy(exp_policy, QSizePolicy.Policy.Preferred)
        self.lbl_camada.setSizePolicy(exp_policy, QSizePolicy.Policy.Preferred)
        
        self.lbl_dedo.setStyleSheet(self.style_field_expanded)
        self.lbl_camada.setStyleSheet(self.style_field_expanded)
    
    def verificar_zip_carregado(self):
        """ Verifica se há um ZIP carregado e exibe mensagem de aviso se necessário. """
        if not hasattr(self, 'media_files') or not self.media_files:
            QMessageBox.warning(
                self, 
                "Ação Bloqueada", 
                "Por favor, carregue um arquivo ZIP primeiro para liberar essa funcionalidade!"
            )
            return False
        return True
    
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
