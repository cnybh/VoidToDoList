import os
import subprocess
import sys
import winreg
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox


APP_NAME = "VoidToDoList"
INSTALL_DIR = os.path.dirname(os.path.abspath(sys.executable))
ICON_PATH = os.path.join(getattr(sys, "_MEIPASS", INSTALL_DIR), "logo.ico")


def remove_installation():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    except OSError:
        pass

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            winreg.DeleteKey(root, r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_NAME)
        except OSError:
            pass

    cleanup = os.path.join(os.environ.get("TEMP", INSTALL_DIR), "VoidToDoList_cleanup.bat")
    desktop_link = os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk")
    start_menu_link = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs", APP_NAME, f"{APP_NAME}.lnk")
    startup_link = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", f"{APP_NAME}.lnk")
    lines = [
        "@echo off", "timeout /t 3 /nobreak >nul",
        f'taskkill /f /im "{APP_NAME}.exe" >nul 2>&1',
        f'del /f /q "{desktop_link}" >nul 2>&1',
        f'del /f /q "{start_menu_link}" >nul 2>&1',
        f'rmdir /s /q "{os.path.dirname(start_menu_link)}" >nul 2>&1',
        f'del /f /q "{startup_link}" >nul 2>&1',
        ":remove_installation",
        f'rmdir /s /q "{INSTALL_DIR}" >nul 2>&1',
        f'if exist "{INSTALL_DIR}" (timeout /t 1 /nobreak >nul & goto remove_installation)',
        'del /f /q "%~f0" >nul 2>&1',
    ]
    with open(cleanup, "w", encoding="utf-8") as target:
        target.write("\n".join(lines))
    subprocess.Popen(["cmd", "/c", cleanup], creationflags=subprocess.CREATE_NO_WINDOW)


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(True)
app.setWindowIcon(QIcon(ICON_PATH))
box = QMessageBox()
box.setWindowTitle(APP_NAME)
box.setWindowIcon(QIcon(ICON_PATH))
box.setText("Are you sure you want to uninstall VoidToDoList?")
box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
box.setDefaultButton(QMessageBox.No)
if box.exec() == QMessageBox.Yes:
    remove_installation()
    # The cleanup script must outlive this executable because it deletes this folder.
    os._exit(0)
sys.exit(0)
