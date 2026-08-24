import json
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QStackedWidget,
    QVBoxLayout, QGridLayout, QWidget,
)


APP_NAME = "VoidToDoList"
VERSION = "1.0"
LANGUAGES = [
    ("简体中文", "zh-CN"), ("繁體中文", "zh-TW"),
    ("English", "en"), ("日本語", "ja"), ("한국어", "ko"),
    ("Français", "fr"), ("Deutsch", "de"), ("Español", "es"),
    ("Português", "pt"), ("Italiano", "it"), ("Русский", "ru"),
    ("ไทย", "th"), ("Bahasa Melayu", "ms"), ("Bahasa Indonesia", "id"),
    ("Tiếng Việt", "vi"), ("हिन्दी", "hi"), ("العربية", "ar"),
]


def resource_path(name):
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), name)


class Installer(QWidget):
    def __init__(self):
        super().__init__()
        self.install_dir = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), APP_NAME)
        self.selected_language = "en"
        self.install_started = False
        self.install_files_copied = False
        self.setWindowTitle(f"{APP_NAME} Setup")
        self.setWindowIcon(QIcon(resource_path("logo.ico")))
        self.setFixedSize(700, 450)
        self.build_ui()

    def build_ui(self):
        self.setStyleSheet("""
            QWidget { font-family: 'Segoe UI'; font-size: 10pt; }
            QLabel#side { background: #f1f3f5; color: #1f2937; font-size: 18pt; font-weight: 600; padding: 28px 20px; }
            QLineEdit { padding: 7px; border: 1px solid #aeb5bd; }
            QPushButton { min-width: 78px; padding: 7px 14px; }
            QListWidget { border: 1px solid #aeb5bd; }
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.side = QWidget()
        self.side.setFixedWidth(190)
        side_layout = QVBoxLayout(self.side)
        side_layout.setContentsMargins(18, 32, 18, 20)
        side_layout.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(QPixmap(resource_path("logo.ico")).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size: 18pt; font-weight: 600; color: #1f2937;")
        name.setAlignment(Qt.AlignHCenter)
        side_layout.addWidget(name)
        side_layout.addStretch()
        root.addWidget(self.side)
        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 18)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.welcome_page())
        self.pages.addWidget(self.location_page())
        self.pages.addWidget(self.progress_page())
        self.pages.addWidget(self.language_page())
        self.pages.addWidget(self.options_page())
        content.addWidget(self.pages, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.next_button = QPushButton("Next >")
        self.next_button.clicked.connect(self.next_page)
        buttons.addWidget(self.next_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)
        buttons.addWidget(self.cancel_button)
        content.addLayout(buttons)
        root.addLayout(content, 1)

    def heading(self, title, text):
        label = QLabel(f"<h2>{title}</h2><p>{text}</p>")
        label.setWordWrap(True)
        return label

    def welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.heading("Welcome to the VoidToDoList Setup Wizard", "This wizard will install VoidToDoList on your computer."))
        layout.addStretch()
        return page

    def location_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.heading("Choose Install Location", "Select the folder where VoidToDoList will be installed."))
        row = QHBoxLayout()
        self.location_edit = QLineEdit(self.install_dir)
        row.addWidget(self.location_edit, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse_location)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addStretch()
        return page

    def progress_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.heading("Installing VoidToDoList", "Please wait while the files are copied."))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.progress_text = QLabel("Ready to install.")
        layout.addWidget(self.progress_text)
        layout.addStretch()
        return page

    def language_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.heading("Choose Language", "Select the language used by VoidToDoList."))
        layout.addSpacing(14)
        self.language_buttons = []
        language_box = QGridLayout()
        language_box.setContentsMargins(0, 0, 0, 0)
        language_box.setHorizontalSpacing(42)
        language_box.setVerticalSpacing(10)
        language_box.setColumnStretch(0, 1)
        language_box.setColumnStretch(1, 1)
        for index, (display, code) in enumerate(LANGUAGES):
            button = QRadioButton(display)
            button.setProperty("language_code", code)
            self.language_buttons.append(button)
            language_box.addWidget(button, index // 2, index % 2)
            if code == "en":
                button.setChecked(True)
        layout.addLayout(language_box)
        layout.addStretch()
        return page

    def options_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.heading("Additional Options", "Choose whether to start VoidToDoList with Windows and open it after setup."))
        layout.addSpacing(14)
        self.startup_check = QCheckBox("Start VoidToDoList with Windows")
        self.desktop_check = QCheckBox("Add a desktop shortcut")
        self.start_menu_check = QCheckBox("Add a Start Menu shortcut")
        self.open_check = QCheckBox("Launch VoidToDoList when setup closes")
        self.startup_check.setChecked(True)
        self.desktop_check.setChecked(True)
        self.start_menu_check.setChecked(True)
        self.open_check.setChecked(True)
        layout.addWidget(self.startup_check)
        layout.addWidget(self.desktop_check)
        layout.addWidget(self.start_menu_check)
        layout.addWidget(self.open_check)
        layout.addStretch()
        return page

    def browse_location(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Install Location", self.location_edit.text())
        if folder:
            self.location_edit.setText(folder)

    def next_page(self):
        current = self.pages.currentIndex()
        if current == 1:
            self.install_dir = self.location_edit.text().strip()
            if not self.install_dir:
                QMessageBox.warning(self, APP_NAME, "Please choose an install location.")
                return
            self.pages.setCurrentIndex(2)
            self.next_button.setEnabled(False)
            self.install_files()
        elif current == 3:
            for button in self.language_buttons:
                if button.isChecked():
                    self.selected_language = button.property("language_code")
                    break
            self.pages.setCurrentIndex(4)
            self.next_button.setText("Finish")
        elif current == 4:
            self.configure_options()
            self.finish_setup()
        else:
            self.pages.setCurrentIndex(current + 1)

    def install_files(self):
        if self.install_started:
            return
        self.install_started = True
        os.makedirs(self.install_dir, exist_ok=True)
        files = ["VoidToDoList.exe", "settings.json", "todos.json", "logo.ico", "VoidToDoList_uninstaller.exe"]
        for name in files:
            source = resource_path(name)
            if os.path.isfile(source):
                shutil.copy2(source, os.path.join(self.install_dir, name))
        self.install_files_copied = True
        self.progress.setValue(0)
        self.progress_text.setText("Copying files...")
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.advance_progress)
        self.progress_timer.start(20)

    def advance_progress(self):
        value = self.progress.value() + 1
        self.progress.setValue(value)
        self.progress_text.setText(f"Installing... {value}%")
        if value >= 100:
            self.progress_timer.stop()
            self.next_button.setEnabled(True)
            QTimer.singleShot(250, lambda: self.pages.setCurrentIndex(3))

    def configure_options(self):
        settings_path = os.path.join(self.install_dir, "settings.json")
        try:
            with open(settings_path, "w", encoding="utf-8") as target:
                json.dump({"language": self.selected_language}, target, ensure_ascii=False, indent=2)
        except OSError:
            pass
        installed_exe = os.path.join(self.install_dir, "VoidToDoList.exe")
        startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
        startup_link = os.path.join(startup_dir, f"{APP_NAME}.lnk")
        if self.desktop_check.isChecked():
            self.create_shortcut(os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk"), installed_exe)
        if self.start_menu_check.isChecked():
            start_menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
            start_menu_folder = os.path.join(start_menu, APP_NAME)
            self.create_shortcut(os.path.join(start_menu_folder, f"{APP_NAME}.lnk"), installed_exe)
        if self.startup_check.isChecked():
            self.create_shortcut(startup_link, installed_exe)
        elif os.path.exists(startup_link):
            os.remove(startup_link)
        self.register_uninstall()

    def create_shortcut(self, shortcut_path, target):
        """Create one explicit .lnk file pointing only to the installed exe."""
        try:
            os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
            def ps_string(value):
                return "'" + value.replace("'", "''") + "'"

            command = (
                "$shell=New-Object -ComObject WScript.Shell;"
                f"$link=$shell.CreateShortcut({ps_string(shortcut_path)});"
                f"$link.TargetPath={ps_string(target)};"
                f"$link.WorkingDirectory={ps_string(self.install_dir)};"
                f"$link.IconLocation={ps_string(target)};"
                "$link.Save()"
            )
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            return False

    def register_uninstall(self):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_NAME
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "bohangyang")
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, self.install_dir)
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, os.path.join(self.install_dir, "logo.ico"))
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, os.path.join(self.install_dir, "VoidToDoList_uninstaller.exe"))
        except OSError:
            pass

    def finish_setup(self):
        launch = self.open_check.isChecked()
        installed_exe = os.path.join(self.install_dir, "VoidToDoList.exe")
        self.close()
        if launch and os.path.isfile(installed_exe):
            subprocess.Popen([installed_exe], cwd=self.install_dir)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Installer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
