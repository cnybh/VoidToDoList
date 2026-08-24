import json
import os
import subprocess
import sys
import winreg
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

# Bundled resources use _MEIPASS; user data stays beside the script or exe.
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
DATA_FILE = os.path.join(APP_DIR, "todos.json")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
WIDTH, HEIGHT = 400, 800

LANGUAGES = [
    ("简体中文", "zh-CN"), ("繁體中文", "zh-TW"), ("English", "en"),
    ("日本語", "ja"), ("한국어", "ko"), ("Français", "fr"),
    ("Deutsch", "de"), ("Español", "es"), ("Português", "pt"),
    ("Italiano", "it"), ("Русский", "ru"), ("ไทย", "th"),
    ("Bahasa Melayu", "ms"), ("Bahasa Indonesia", "id"),
    ("Tiếng Việt", "vi"), ("हिन्दी", "hi"), ("العربية", "ar"),
]

TRANSLATIONS = {
    "zh-CN": {"title":"待办事项", "placeholder":"添加待办事项", "add":"添加待办", "empty":"暂无待办事项", "done":"完成待办", "delete":"删除待办", "delete_q":"彻底删除本待办？", "confirm":"确认", "cancel":"取消", "settings":"设置", "about":"关于", "exit":"退出", "exit_q":"是否确定退出", "startup":"检查和设置启动项", "language":"更改语言：", "version":"当前版本：v1.0", "release":"软件发布页", "close":"关闭", "developer":"VoidToDoList 由 bohangyang 开发", "description":"极简的工作待办事项助手", "email":"作者邮箱："},
    "zh-TW": {"title":"待辦事項", "placeholder":"新增待辦事項", "add":"新增待辦", "empty":"目前沒有待辦事項", "done":"完成待辦", "delete":"刪除待辦", "delete_q":"徹底刪除這項待辦？", "confirm":"確認", "cancel":"取消", "settings":"設定", "about":"關於", "exit":"退出", "exit_q":"是否確定退出", "startup":"檢查和設定啟動項", "language":"更改語言：", "version":"目前版本：v1.0", "release":"軟體發布頁", "close":"關閉", "developer":"VoidToDoList 由 bohangyang 開發", "description":"極簡的工作待辦事項助手", "email":"作者信箱："},
    "en": {"title":"To-Do List", "placeholder":"Add a task", "add":"Add task", "empty":"No tasks", "done":"Complete task", "delete":"Delete task", "delete_q":"Delete this task permanently?", "confirm":"Confirm", "cancel":"Cancel", "settings":"Settings", "about":"About", "exit":"Exit", "exit_q":"Are you sure you want to exit?", "startup":"Check and set startup", "language":"Change language:", "version":"Current version: v1.0", "release":"Release page", "close":"Close", "developer":"VoidToDoList developed by bohangyang", "description":"A minimal work to-do assistant", "email":"Email: "},
    "ja": {"title":"ToDoリスト", "placeholder":"タスクを追加", "add":"タスクを追加", "empty":"タスクはありません", "done":"タスクを完了", "delete":"タスクを削除", "delete_q":"このタスクを完全に削除しますか？", "confirm":"確認", "cancel":"キャンセル", "settings":"設定", "about":"概要", "exit":"終了", "exit_q":"終了してもよろしいですか？", "startup":"スタートアップを確認・設定", "language":"言語を変更：", "version":"現在のバージョン：v1.0", "release":"リリースページ", "close":"閉じる", "developer":"VoidToDoList 開発者 bohangyang", "description":"シンプルな仕事用ToDoアシスタント", "email":"メール："},
    "ko": {"title":"할 일 목록", "placeholder":"할 일 추가", "add":"할 일 추가", "empty":"할 일이 없습니다", "done":"완료", "delete":"삭제", "delete_q":"이 할 일을 완전히 삭제할까요?", "confirm":"확인", "cancel":"취소", "settings":"설정", "about":"정보", "exit":"종료", "exit_q":"종료하시겠습니까?", "startup":"시작 항목 확인 및 설정", "language":"언어 변경:", "version":"현재 버전: v1.0", "release":"릴리스 페이지", "close":"닫기", "developer":"VoidToDoList 개발자 bohangyang", "description":"간단한 업무 할 일 도우미", "email":"이메일: "},
    "fr": {"title":"Liste de tâches", "placeholder":"Ajouter une tâche", "add":"Ajouter", "empty":"Aucune tâche", "done":"Terminer", "delete":"Supprimer", "delete_q":"Supprimer définitivement cette tâche ?", "confirm":"Confirmer", "cancel":"Annuler", "settings":"Paramètres", "about":"À propos", "exit":"Quitter", "exit_q":"Voulez-vous vraiment quitter ?", "startup":"Vérifier et configurer le démarrage", "language":"Changer de langue :", "version":"Version actuelle : v1.0", "release":"Page de publication", "close":"Fermer", "developer":"VoidToDoList développé par bohangyang", "description":"Un assistant de tâches professionnel minimaliste", "email":"E-mail : "},
    "de": {"title":"Aufgabenliste", "placeholder":"Aufgabe hinzufügen", "add":"Hinzufügen", "empty":"Keine Aufgaben", "done":"Aufgabe erledigen", "delete":"Aufgabe löschen", "delete_q":"Diese Aufgabe dauerhaft löschen?", "confirm":"Bestätigen", "cancel":"Abbrechen", "settings":"Einstellungen", "about":"Über", "exit":"Beenden", "exit_q":"Möchten Sie wirklich beenden?", "startup":"Autostart prüfen und festlegen", "language":"Sprache ändern:", "version":"Aktuelle Version: v1.0", "release":"Veröffentlichungsseite", "close":"Schließen", "developer":"VoidToDoList entwickelt von bohangyang", "description":"Ein minimalistischer Assistent für Arbeitsaufgaben", "email":"E-Mail: "},
    "es": {"title":"Lista de tareas", "placeholder":"Añadir tarea", "add":"Añadir", "empty":"No hay tareas", "done":"Completar tarea", "delete":"Eliminar tarea", "delete_q":"¿Eliminar esta tarea permanentemente?", "confirm":"Confirmar", "cancel":"Cancelar", "settings":"Ajustes", "about":"Acerca de", "exit":"Salir", "exit_q":"¿Está seguro de que desea salir?", "startup":"Comprobar y configurar inicio", "language":"Cambiar idioma:", "version":"Versión actual: v1.0", "release":"Página de publicación", "close":"Cerrar", "developer":"VoidToDoList desarrollado por bohangyang", "description":"Un asistente minimalista de tareas de trabajo", "email":"Correo: "},
    "pt": {"title":"Lista de tarefas", "placeholder":"Adicionar tarefa", "add":"Adicionar", "empty":"Sem tarefas", "done":"Concluir tarefa", "delete":"Excluir tarefa", "delete_q":"Excluir esta tarefa permanentemente?", "confirm":"Confirmar", "cancel":"Cancelar", "settings":"Configurações", "about":"Sobre", "exit":"Sair", "exit_q":"Tem certeza de que deseja sair?", "startup":"Verificar e configurar inicialização", "language":"Alterar idioma:", "version":"Versão atual: v1.0", "release":"Página de lançamento", "close":"Fechar", "developer":"VoidToDoList desenvolvido por bohangyang", "description":"Um assistente minimalista de tarefas de trabalho", "email":"E-mail: "},
    "it": {"title":"Elenco attività", "placeholder":"Aggiungi attività", "add":"Aggiungi", "empty":"Nessuna attività", "done":"Completa attività", "delete":"Elimina attività", "delete_q":"Eliminare definitivamente questa attività?", "confirm":"Conferma", "cancel":"Annulla", "settings":"Impostazioni", "about":"Informazioni", "exit":"Esci", "exit_q":"Vuoi davvero uscire?", "startup":"Controlla e configura l'avvio", "language":"Cambia lingua:", "version":"Versione attuale: v1.0", "release":"Pagina di rilascio", "close":"Chiudi", "developer":"VoidToDoList sviluppato da bohangyang", "description":"Un assistente minimalista per le attività di lavoro", "email":"E-mail: "},
    "ru": {"title":"Список дел", "placeholder":"Добавить задачу", "add":"Добавить", "empty":"Нет задач", "done":"Выполнить задачу", "delete":"Удалить задачу", "delete_q":"Удалить эту задачу навсегда?", "confirm":"Подтвердить", "cancel":"Отмена", "settings":"Настройки", "about":"О программе", "exit":"Выход", "exit_q":"Вы действительно хотите выйти?", "startup":"Проверить и настроить автозапуск", "language":"Изменить язык:", "version":"Текущая версия: v1.0", "release":"Страница релиза", "close":"Закрыть", "developer":"VoidToDoList разработан bohangyang", "description":"Минималистичный помощник для рабочих задач", "email":"Эл. почта: "},
    "th": {"title":"รายการสิ่งที่ต้องทำ", "placeholder":"เพิ่มงาน", "add":"เพิ่มงาน", "empty":"ไม่มีงาน", "done":"ทำงานเสร็จ", "delete":"ลบงาน", "delete_q":"ลบงานนี้อย่างถาวรหรือไม่?", "confirm":"ยืนยัน", "cancel":"ยกเลิก", "settings":"การตั้งค่า", "about":"เกี่ยวกับ", "exit":"ออก", "exit_q":"ต้องการออกหรือไม่?", "startup":"ตรวจสอบและตั้งค่าการเริ่มต้น", "language":"เปลี่ยนภาษา:", "version":"เวอร์ชันปัจจุบัน: v1.0", "release":"หน้ารุ่นเผยแพร่", "close":"ปิด", "developer":"VoidToDoList พัฒนาโดย bohangyang", "description":"ผู้ช่วยงานแบบเรียบง่าย", "email":"อีเมล: "},
    "ms": {"title":"Senarai Tugasan", "placeholder":"Tambah tugasan", "add":"Tambah", "empty":"Tiada tugasan", "done":"Selesaikan tugasan", "delete":"Padam tugasan", "delete_q":"Padam tugasan ini secara kekal?", "confirm":"Sahkan", "cancel":"Batal", "settings":"Tetapan", "about":"Perihal", "exit":"Keluar", "exit_q":"Adakah anda pasti mahu keluar?", "startup":"Semak dan tetapkan permulaan", "language":"Tukar bahasa:", "version":"Versi semasa: v1.0", "release":"Halaman keluaran", "close":"Tutup", "developer":"VoidToDoList dibangunkan oleh bohangyang", "description":"Pembantu tugasan kerja yang ringkas", "email":"E-mel: "},
    "id": {"title":"Daftar Tugas", "placeholder":"Tambah tugas", "add":"Tambah", "empty":"Tidak ada tugas", "done":"Selesaikan tugas", "delete":"Hapus tugas", "delete_q":"Hapus tugas ini secara permanen?", "confirm":"Konfirmasi", "cancel":"Batal", "settings":"Pengaturan", "about":"Tentang", "exit":"Keluar", "exit_q":"Yakin ingin keluar?", "startup":"Periksa dan atur mulai otomatis", "language":"Ubah bahasa:", "version":"Versi saat ini: v1.0", "release":"Halaman rilis", "close":"Tutup", "developer":"VoidToDoList dikembangkan oleh bohangyang", "description":"Asisten tugas kerja minimalis", "email":"Email: "},
    "vi": {"title":"Danh sách việc cần làm", "placeholder":"Thêm công việc", "add":"Thêm", "empty":"Chưa có công việc", "done":"Hoàn thành", "delete":"Xóa công việc", "delete_q":"Xóa vĩnh viễn công việc này?", "confirm":"Xác nhận", "cancel":"Hủy", "settings":"Cài đặt", "about":"Giới thiệu", "exit":"Thoát", "exit_q":"Bạn có chắc muốn thoát không?", "startup":"Kiểm tra và đặt khởi động", "language":"Đổi ngôn ngữ:", "version":"Phiên bản hiện tại: v1.0", "release":"Trang phát hành", "close":"Đóng", "developer":"VoidToDoList được phát triển bởi bohangyang", "description":"Trợ lý công việc tối giản", "email":"Email: "},
    "hi": {"title":"कार्य सूची", "placeholder":"कार्य जोड़ें", "add":"जोड़ें", "empty":"कोई कार्य नहीं", "done":"कार्य पूरा करें", "delete":"कार्य हटाएं", "delete_q":"क्या यह कार्य स्थायी रूप से हटाएं?", "confirm":"पुष्टि करें", "cancel":"रद्द करें", "settings":"सेटिंग्स", "about":"हमारे बारे में", "exit":"बाहर निकलें", "exit_q":"क्या आप बाहर निकलना चाहते हैं?", "startup":"स्टार्टअप जांचें और सेट करें", "language":"भाषा बदलें:", "version":"वर्तमान संस्करण: v1.0", "release":"रिलीज़ पेज", "close":"बंद करें", "developer":"VoidToDoList bohangyang द्वारा विकसित", "description":"सरल कार्य सहायक", "email":"ईमेल: "},
    "ar": {"title":"قائمة المهام", "placeholder":"إضافة مهمة", "add":"إضافة", "empty":"لا توجد مهام", "done":"إكمال المهمة", "delete":"حذف المهمة", "delete_q":"هل تريد حذف هذه المهمة نهائياً؟", "confirm":"تأكيد", "cancel":"إلغاء", "settings":"الإعدادات", "about":"حول", "exit":"خروج", "exit_q":"هل أنت متأكد من الخروج؟", "startup":"فحص إعداد بدء التشغيل", "language":"تغيير اللغة:", "version":"الإصدار الحالي: v1.0", "release":"صفحة الإصدار", "close":"إغلاق", "developer":"تم تطوير VoidToDoList بواسطة bohangyang", "description":"مساعد مهام عمل بسيط", "email":"البريد الإلكتروني: "},
}


class CompletionButton(QPushButton):
    """Transparent completion control drawn consistently at any DPI."""
    def __init__(self, completed):
        super().__init__()
        self.completed = completed
        self.setFixedSize(42, 42)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: rgba(255,255,255,30); } QPushButton:pressed { background: rgba(255,255,255,50); }")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("white"))
        painter.drawRect(12, 12, 17, 17)
        if self.completed:
            painter.drawLine(15, 15, 26, 26)
            painter.drawLine(26, 15, 15, 26)


class TodoDesktop(QWidget):
    """Desktop to-do panel, tray menu, settings, and persistent task storage."""

    def __init__(self):
        super().__init__()
        self.language = self.load_language()
        QApplication.instance().setLayoutDirection(Qt.RightToLeft if self.language == "ar" else Qt.LeftToRight)
        self.todos = self.load_todos()
        self._allow_close = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self.build_ui()
        self.position_window()
        self.create_tray_icon()

    def load_language(self):
        # Language is kept separately so changing it never touches task data.
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as source:
                code = json.load(source).get("language", "zh-CN")
            return code if code in TRANSLATIONS else "zh-CN"
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return "zh-CN"

    def save_language(self):
        try:
            with open(SETTINGS_FILE + ".tmp", "w", encoding="utf-8") as target:
                json.dump({"language": self.language}, target, ensure_ascii=False, indent=2)
            os.replace(SETTINGS_FILE + ".tmp", SETTINGS_FILE)
        except OSError:
            pass

    def tr(self, key):
        return TRANSLATIONS[self.language].get(key, TRANSLATIONS["en"].get(key, key))

    def set_language(self, code):
        # Update all currently visible surfaces immediately, including RTL mode.
        self.language = code
        self.save_language()
        QApplication.instance().setLayoutDirection(Qt.RightToLeft if code == "ar" else Qt.LeftToRight)
        self.title_label.setText(self.tr("title"))
        self.entry.setPlaceholderText(self.tr("placeholder"))
        self.add_button.setToolTip(self.tr("add"))
        self.tray.setToolTip("VoidToDoList")
        self.tray_menu.actions()[0].setText(self.tr("settings"))
        self.tray_menu.actions()[1].setText(self.tr("about"))
        self.tray_menu.actions()[-1].setText(self.tr("exit"))
        if hasattr(self, "settings_startup"):
            self.settings_startup.setText(self.tr("startup"))
            self.settings_language_label.setText(self.tr("language"))
            self.settings_version.setText(self.tr("version"))
            self.settings_release.setText(f'<a href="https://github.com/cnybh/VoidToDoList">{self.tr("release")}</a>')
            self.settings_close.setText(self.tr("close"))
        self.refresh_list()

    def load_todos(self):
        # Completed tasks are retained for the current day and removed next day.
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as source:
                todos = json.load(source)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            todos = []
        today = date.today().isoformat()
        self.todos = [todo for todo in todos if not (todo.get("done") and todo.get("done_date") != today)]
        self.save_todos()
        return self.todos

    def save_todos(self):
        # Replace through a temporary file to avoid partially written JSON.
        try:
            with open(DATA_FILE + ".tmp", "w", encoding="utf-8") as target:
                json.dump(self.todos, target, ensure_ascii=False, indent=2)
            os.replace(DATA_FILE + ".tmp", DATA_FILE)
        except OSError:
            pass

    def build_ui(self):
        # The main window is transparent; only the input field has a visible fill.
        self.setStyleSheet("""
            QWidget { color: white; font-family: 'Microsoft YaHei UI'; }
            QLineEdit { background: rgba(255,255,255,26); border: none; color: white; font-size: 12pt; padding: 8px 10px; }
            QLineEdit:focus { background: rgba(255,255,255,38); }
            QScrollArea, QScrollArea::viewport { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 5px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,45); min-height: 25px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)
        outer.setSpacing(12)
        title = QLabel(self.tr("title"))
        title.setStyleSheet("font-size: 16pt; font-weight: 600; background: transparent;")
        self.title_label = title
        outer.addWidget(title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setAttribute(Qt.WA_TranslucentBackground)
        self.scroll.viewport().setAutoFillBackground(False)
        self.list_widget = QWidget()
        self.list_widget.setAttribute(Qt.WA_TranslucentBackground)
        self.list_widget.setAutoFillBackground(False)
        self.list_widget.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(5)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.list_widget)
        outer.addWidget(self.scroll, 1)
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText(self.tr("placeholder"))
        self.entry.setMinimumHeight(42)
        self.entry.returnPressed.connect(self.add_todo)
        add_row.addWidget(self.entry, 1)
        add_button = self.action_button("+", 48)
        add_button.setToolTip(self.tr("add"))
        add_button.clicked.connect(self.add_todo)
        self.add_button = add_button
        add_row.addWidget(add_button)
        outer.addLayout(add_row)
        self.refresh_list()

    def action_button(self, text, width, transparent=False):
        button = QPushButton(text)
        button.setFixedSize(width, 42)
        button.setCursor(Qt.PointingHandCursor)
        background = "transparent" if transparent else "rgba(255,255,255,26)"
        button.setStyleSheet(f"QPushButton {{ background: {background}; border: none; color: white; font-size: 20pt; }} QPushButton:hover {{ background: rgba(255,255,255,30); }} QPushButton:pressed {{ background: rgba(255,255,255,50); }}")
        return button

    def refresh_list(self):
        # Rebuild rows so text wrapping, completion state, and translations stay in sync.
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.todos:
            empty = QLabel(self.tr("empty"))
            empty.setStyleSheet("color: rgba(255,255,255,170); padding: 8px 0;")
            self.list_layout.addWidget(empty)
            return
        for index, todo in enumerate(self.todos):
            row = QFrame()
            row.setMinimumHeight(46)
            row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            row.setStyleSheet("background: transparent; border: none;")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 2, 3, 2)
            layout.setSpacing(6)
            check = CompletionButton(todo.get("done", False))
            check.setToolTip(self.tr("done"))
            check.clicked.connect(lambda _checked=False, i=index: self.toggle_done(i))
            layout.addWidget(check)
            label = QLabel(todo.get("text", ""))
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label.setStyleSheet("font-size: 12pt; color: rgba(255,255,255,145); text-decoration: line-through;" if todo.get("done") else "font-size: 12pt; color: white;")
            layout.addWidget(label, 1)
            remove = self.action_button("×", 42, transparent=True)
            remove.setToolTip(self.tr("delete"))
            remove.clicked.connect(lambda _checked=False, i=index: self.delete_todo(i))
            layout.addWidget(remove)
            self.list_layout.addWidget(row)

    def add_todo(self):
        text = self.entry.text().strip()
        if text:
            self.todos.append({"text": text, "done": False, "done_date": None})
            self.entry.clear()
            self.save_todos()
            self.refresh_list()

    def toggle_done(self, index):
        checked = not self.todos[index]["done"]
        self.todos[index]["done"] = checked
        self.todos[index]["done_date"] = date.today().isoformat() if checked else None
        self.save_todos()
        self.refresh_list()

    def delete_todo(self, index):
        confirmation = QMessageBox(self)
        confirmation.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        confirmation.setText(self.tr("delete_q"))
        confirmation.setWindowTitle("VoidToDoList")
        confirmation.setWindowIcon(QIcon())
        confirmation.setIcon(QMessageBox.NoIcon)
        confirmation.setStyleSheet("QMessageBox { color: black; } QMessageBox QLabel { color: black; } QMessageBox QPushButton { color: black; min-width: 72px; }")
        confirmation.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirmation.setButtonText(QMessageBox.Yes, self.tr("confirm"))
        confirmation.setButtonText(QMessageBox.No, self.tr("cancel"))
        confirmation.setDefaultButton(QMessageBox.No)
        if confirmation.exec() != QMessageBox.Yes:
            return
        del self.todos[index]
        self.save_todos()
        self.refresh_list()

    def position_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + int(screen.width() * .75 - WIDTH / 2), screen.y() + int(screen.height() * .5 - HEIGHT / 2))

    def create_tray_icon(self):
        # The tray is the only supported way to reach settings or exit.
        icon_path = os.path.join(RESOURCE_DIR, "logo.ico")
        icon = QIcon(icon_path)
        if icon.isNull():
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setBrush(QColor("#4f8cff"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(8, 8, 48, 48, 10, 10)
            painter.setPen(QColor("white"))
            painter.drawLine(20, 32, 29, 41)
            painter.drawLine(29, 41, 46, 22)
            painter.end()
            icon = QIcon(pixmap)
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        settings_action = QAction(self.tr("settings"), self)
        settings_action.triggered.connect(self.open_settings)
        about_action = QAction(self.tr("about"), self)
        about_action.triggered.connect(self.open_about)
        exit_action = QAction(self.tr("exit"), self)
        exit_action.triggered.connect(self.confirm_exit)
        menu.addAction(settings_action)
        menu.addAction(about_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(self.tr("title"))
        self.tray.show()

    def startup_enabled(self):
        """Check the current-user Startup folder instead of the Run registry key."""
        return os.path.isfile(self.startup_shortcut_path())

    def startup_shortcut_path(self):
        startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
        return os.path.join(startup_dir, "VoidToDoList.lnk")

    def set_startup(self, enabled):
        # A Startup-folder shortcut avoids modifying the Run registry key.
        shortcut = self.startup_shortcut_path()
        try:
            if not enabled:
                if os.path.exists(shortcut):
                    os.remove(shortcut)
                return True
            os.makedirs(os.path.dirname(shortcut), exist_ok=True)
            target = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
            def ps_string(value):
                return "'" + value.replace("'", "''") + "'"

            ps = (
                "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + ps_string(shortcut) + ");"
                "$s.TargetPath=" + ps_string(target) + ";"
                "$s.WorkingDirectory=" + ps_string(os.path.dirname(target)) + ";"
                "$s.Save()"
            )
            subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=15)
            return self.startup_enabled()
        except (OSError, subprocess.SubprocessError):
            return False

    def handle_startup_toggle(self, enabled, checkbox):
        """Apply the setting and keep the checkbox aligned with the registry."""
        if self.set_startup(enabled):
            return
        checkbox.blockSignals(True)
        checkbox.setChecked(self.startup_enabled())
        checkbox.blockSignals(False)
        QMessageBox.warning(self, "VoidToDoList", "无法修改 Windows 自启动设置。")

    def open_settings(self):
        # Settings are deliberately modal so a language change is immediately visible.
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle("VoidToDoList")
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setStyleSheet("""
            QDialog { background: white; color: black; }
            QLabel, QCheckBox { color: black; }
            QComboBox { color: black; background: white; min-width: 150px; padding: 4px; }
            QComboBox QAbstractItemView { color: black; background: white; selection-color: black; selection-background-color: #e5e5e5; }
            QPushButton { color: black; background: #f2f2f2; border: 1px solid #b8b8b8; padding: 5px 16px; }
            QPushButton:hover { background: #e5e5e5; }
            QLabel#link { color: #0563c1; text-decoration: underline; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        startup = QCheckBox(self.tr("startup"))
        self.settings_startup = startup
        startup.setChecked(self.startup_enabled())
        startup.toggled.connect(lambda enabled, box=startup: self.handle_startup_toggle(enabled, box))
        layout.addWidget(startup)
        language_row = QHBoxLayout()
        language_label = QLabel(self.tr("language"))
        self.settings_language_label = language_label
        language_row.addWidget(language_label)
        language = QComboBox()
        language.addItems([name for name, _code in LANGUAGES])
        current_index = [code for _name, code in LANGUAGES].index(self.language)
        language.setCurrentIndex(current_index)
        language.currentIndexChanged.connect(lambda index: self.set_language(LANGUAGES[index][1]))
        language_row.addWidget(language)
        layout.addLayout(language_row)
        version_row = QHBoxLayout()
        version_row.setSpacing(12)
        version_label = QLabel(self.tr("version"))
        version_label.setStyleSheet("color: black;")
        self.settings_version = version_label
        version_row.addWidget(version_label)
        link = QLabel(f'<a href="https://github.com/cnybh/VoidToDoList">{self.tr("release")}</a>')
        link.setObjectName("link")
        link.setOpenExternalLinks(True)
        link.setCursor(Qt.PointingHandCursor)
        self.settings_release = link
        version_row.addWidget(link)
        version_row.addStretch()
        layout.addLayout(version_row)
        close_button = QPushButton(self.tr("close"))
        self.settings_close = close_button
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)
        dialog.finished.connect(lambda _result: self.clear_settings_refs())
        dialog.exec()

    def clear_settings_refs(self):
        for name in ("settings_startup", "settings_language_label", "settings_version", "settings_release", "settings_close"):
            if hasattr(self, name):
                delattr(self, name)

    def open_about(self):
        # Keep the about dialog independent from the desktop panel styling.
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle("VoidToDoList")
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setStyleSheet("QDialog { background: white; color: black; } QLabel { color: black; } QPushButton { color: black; background: #f2f2f2; border: 1px solid #b8b8b8; padding: 5px 16px; }")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        developer = QLabel(self.tr("developer"))
        description = QLabel(self.tr("description"))
        email = QLabel(f'{self.tr("email")}<a href="mailto:bohangyang985@hotmail.com">bohangyang985@hotmail.com</a>')
        email.setStyleSheet("QLabel { color: black; } QLabel a { color: #0563c1; }")
        email.setOpenExternalLinks(True)
        email.setCursor(Qt.PointingHandCursor)
        layout.addWidget(developer)
        layout.addWidget(description)
        layout.addWidget(email)
        close_button = QPushButton(self.tr("close"))
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)
        dialog.exec()

    def confirm_exit(self):
        # Explicit cleanup is required because the main window ignores normal close events.
        confirmation = QMessageBox(self)
        confirmation.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        confirmation.setAttribute(Qt.WA_DeleteOnClose)
        confirmation.setIcon(QMessageBox.NoIcon)
        confirmation.setText(self.tr("exit_q"))
        confirmation.setWindowTitle("VoidToDoList")
        confirmation.setWindowIcon(QIcon())
        confirmation.setStyleSheet("QMessageBox { color: black; } QMessageBox QLabel { color: black; } QMessageBox QPushButton { color: black; min-width: 72px; }")
        confirmation.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirmation.setButtonText(QMessageBox.Yes, self.tr("confirm"))
        confirmation.setButtonText(QMessageBox.No, self.tr("cancel"))
        confirmation.setDefaultButton(QMessageBox.No)
        if confirmation.exec() == QMessageBox.Yes:
            self.save_todos()
            self._allow_close = True
            self.tray.setContextMenu(None)
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None
            self.hide()
            self.close()
            QApplication.instance().exit(0)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 13))


def main():
    # Keep UI dimensions in logical pixels and let Qt scale them for Windows DPI.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = TodoDesktop()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
