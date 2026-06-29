LANGUAGES = [
    "", "English 🇬🇧", "Ukrainian 🇺🇦", "Russian 🇺🇦", "German 🇩🇪", "French 🇫🇷",
    "Spanish 🇪🇸", "Italian 🇮🇹", "Polish 🇵🇱", "Portuguese 🇵🇹", "Dutch 🇳🇱",
    "Swedish 🇸🇪", "Czech 🇨🇿", "Greek 🇬🇷", "Romanian 🇷🇴", "Hungarian 🇭🇺",
    "Bulgarian 🇧🇬", "Danish 🇩🇰", "Finnish 🇫🇮", "Norwegian 🇳🇴", "Slovak 🇸🇰",
    "Croatian 🇭🇷", "Lithuanian 🇱🇹", "Slovenian 🇸🇮", "Latvian 🇱🇻", "Estonian 🇪🇪"
]

CONTEXT_SIZES = ["2048", "4096", "8192", "16384", "32768"]

CYRILLIC_LANGUAGES = {"Russian 🇺🇦", "Ukrainian 🇺🇦", "Bulgarian 🇧🇬"}

VALID_EXTENSIONS = {".txt", ".epub"}

STYLESHEET = """
QMainWindow, QWidget { background: #0f1117; color: #e2e8f0; font-family: 'monospace'; font-size: 13px; }
QGroupBox { border: 1px solid #1e2d3d; border-radius: 10px; margin-top: 14px; padding: 14px 12px 10px 12px; font-weight: 600; color: #38bdf8; text-transform: uppercase; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 0 6px; background: #0f1117; }
QPushButton { background: #0ea5e9; color: #0f1117; border: none; border-radius: 7px; padding: 8px 20px; font-weight: 700; }
QPushButton:hover { background: #38bdf8; }
QPushButton:disabled { background: #1e2d3d; color: #475569; }
QPushButton#cancel { background: #1e293b; color: #f87171; border: 1px solid #7f1d1d; }
QPushButton#cancel:hover { background: #7f1d1d; color: #fff; }
QPushButton#small { background: #1e293b; color: #94a3b8; padding: 6px 12px; font-size: 12px; border: 1px solid #1e2d3d; }
QPushButton#small:hover { background: #0ea5e9; color: #0f1117; }
QLineEdit, QSpinBox, QComboBox { background: #0d1520; border: 1px solid #1e2d3d; border-radius: 7px; padding: 7px 11px; color: #e2e8f0; }
QComboBox:on { padding-top: 9px; padding-left: 13px; }
QComboBox::drop-down { border: none; background: transparent; width: 24px; }
QComboBox::down-arrow { image: none; border: none; width: 0px; }
QComboBox QAbstractItemView { background: #0d1520; color: #e2e8f0; selection-background-color: #0ea5e9; border: 1px solid #1e2d3d; border-radius: 7px; padding: 4px 0; outline: none; }
QComboBox QAbstractItemView::item { padding: 6px 11px; min-height: 22px; border: none; }
QComboBox QAbstractItemView::item:hover { background: #1e2d3d; color: #e2e8f0; }
QComboBox QAbstractItemView::item:selected { background: #0ea5e9; color: #0f1117; }
QScrollBar:vertical { background: #0d1520; border: none; width: 8px; margin: 0; border-radius: 4px; }
QScrollBar::handle:vertical { background: #1e2d3d; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #0ea5e9; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QProgressBar { background: #0d1520; border: 1px solid #1e2d3d; border-radius: 7px; text-align: center; color: #94a3b8; height: 22px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #38bdf8); border-radius: 6px; }
QTextEdit { background: #080d14; border: 1px solid #1e2d3d; border-radius: 8px; padding: 10px; color: #4ade80; }
QLabel { color: #94a3b8; }
QLabel#hero { color: #38bdf8; font-size: 22px; font-weight: 800; }
"""
