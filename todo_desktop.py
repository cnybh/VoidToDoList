import json
import os
import subprocess
import sys
import time
import warnings
import ctypes
from ctypes import wintypes
from datetime import date, timedelta

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, QPoint, QLockFile
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)

# Bundled resources use _MEIPASS; user data stays in the user's Documents folder.
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
def documents_directory():
    if os.name == "nt":
        try:
            buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
            if result == 0 and buffer.value:
                return buffer.value
        except (AttributeError, OSError):
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")

USER_DATA_DIR = os.path.join(documents_directory(), "VoidToDoList")
try:
    os.makedirs(USER_DATA_DIR, exist_ok=True)
except OSError:
    pass
DATA_FILE = os.path.join(USER_DATA_DIR, "todos.json")
SETTINGS_FILE = os.path.join(USER_DATA_DIR, "settings.json")
WORD_FILE = os.path.join(USER_DATA_DIR, "word.ini")
LEGACY_DATA_FILE = os.path.join(APP_DIR, "todos.json")
LEGACY_SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")

def migrate_legacy_file(target, legacy, default):
    if os.path.exists(target):
        return
    try:
        if os.path.exists(legacy):
            with open(legacy, "rb") as source, open(target, "wb") as destination:
                destination.write(source.read())
        else:
            with open(target, "w", encoding="utf-8") as destination:
                json.dump(default, destination, ensure_ascii=False, indent=2)
    except OSError:
        pass

# Archived done-task retention: option codes, their day counts (None = keep
# forever), and the value written into a brand-new or pre-retention settings
# file.  Default is two years.
RETENTION_OPTIONS = ("2m", "6m", "1y", "2y", "5y", "never")
RETENTION_DAYS = {"2m": 60, "6m": 183, "1y": 365, "2y": 730, "5y": 1825, "never": None}
RETENTION_LABEL_KEYS = {"2m": "retention_2m", "6m": "retention_6m", "1y": "retention_1y", "2y": "retention_2y", "5y": "retention_5y", "never": "retention_never"}
DEFAULT_RETENTION = "2y"

# Typed-date conventions per language.  Qt's own locale patterns use two-digit
# years and day/month orders that collide, so explicit patterns are used with a
# 4-digit year.  DATE_INPUT_ORDER tells the parser how the typed numbers map to
# (year, month, day) when a language does not write dates year-first.
DATE_INPUT_FORMATS = {
    "en": "%Y-%m-%d", "zh-CN": "%Y-%m-%d", "zh-TW": "%Y-%m-%d", "zh-HK": "%Y-%m-%d",
    "ja": "%Y-%m-%d", "ko": "%Y-%m-%d", "ar": "%Y-%m-%d", "hi": "%Y-%m-%d",
    "th": "%Y-%m-%d", "vi": "%Y-%m-%d", "id": "%Y-%m-%d", "ms": "%Y-%m-%d",
    "ru": "%d.%m.%Y", "de": "%d.%m.%Y",
    "fr": "%d/%m/%Y", "es": "%d/%m/%Y", "it": "%d/%m/%Y", "pt": "%d/%m/%Y",
}
DATE_INPUT_ORDER = {
    "en": "ymd", "zh-CN": "ymd", "zh-TW": "ymd", "zh-HK": "ymd",
    "ja": "ymd", "ko": "ymd", "ar": "ymd", "hi": "ymd",
    "th": "ymd", "vi": "ymd", "id": "ymd", "ms": "ymd",
    "ru": "dmy", "de": "dmy",
    "fr": "dmy", "es": "dmy", "it": "dmy", "pt": "dmy",
}

migrate_legacy_file(DATA_FILE, LEGACY_DATA_FILE, [])
migrate_legacy_file(SETTINGS_FILE, LEGACY_SETTINGS_FILE, {"language":"en","display_mode":"drawer","opacity":25,"drawer_style":"standard","retention":DEFAULT_RETENTION})
WIDTH, HEIGHT = 400, 800
MIN_HEIGHT = HEIGHT  # Height-adjustment lower bound: the window may only grow taller than the default.

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as source:
            value = json.load(source)
        return value if isinstance(value, type(default)) else default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default

def atomic_write_json(path, payload):
    """Write JSON through a temp file + replace. Returns True on success."""
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2)
        os.replace(path + ".tmp", path)
        return True
    except OSError:
        try:
            if os.path.exists(path + ".tmp"):
                os.remove(path + ".tmp")
        except OSError:
            pass
        return False

def screen_ui_scale():
    screen = QApplication.primaryScreen()
    if screen is None:
        return 1.0
    geometry = screen.availableGeometry()
    return min(geometry.width() / 1920.0, geometry.height() / 1080.0)

APP_VERSION = "v1.2"
DEFAULT_AI_PROMPT = (
    "Please process my work list according to the following rules:\n\n"
    "1. Combine similar items (merge items within the same project/task), "
    "separate different items; expand simple items, abbreviate lengthy items; "
    "label each item with status and date, and display in a list.\n\n"
    "2. Output four parts:\n\n"
    "- Overview: 2-4 sentences summarizing overall progress and highlights\n\n"
    "- Detailed Execution: Detailed explanation of content, status, and results for each item\n\n"
    "- Follow-up Arrangements: Next steps and timelines\n\n"
    "- Coordination Required: Difficulties, resource or support needs\n\n"
    "Below is my original work list (please process):\n"
)
LANGUAGE_DIR = os.path.join(RESOURCE_DIR, "languages")

def load_language_catalog():
    catalog = {}
    try:
        for filename in sorted(os.listdir(LANGUAGE_DIR)):
            if not filename.lower().endswith(".json"):
                continue
            code = filename[:-5]
            try:
                with open(os.path.join(LANGUAGE_DIR, filename), "r", encoding="utf-8") as source:
                    package = json.load(source)
                if package.get("code") != code or not isinstance(package.get("translations"), dict):
                    continue
                package.setdefault("name", code)
                catalog[code] = package
            except (OSError, json.JSONDecodeError):
                continue
    except OSError:
        pass
    return catalog

BUILTIN_EN = {
    "title": "To-Do List", "placeholder": "Add a task", "add": "Add task", "empty": "No tasks",
    "done": "Complete task", "delete": "Delete task", "delete_q": "Delete this task permanently?", "confirm": "Confirm", "cancel": "Cancel",
    "settings": "Settings", "about": "About", "exit": "Exit", "exit_q": "Are you sure you want to exit?", "startup": "Check and set startup",
    "language": "Change language:", "mode": "Display mode:", "fixed": "Fixed mode", "drawer": "Drawer mode", "opacity": "Opacity:",
    "drawer_open": "<< Show to-do list", "drawer_close": ">> Hide to-do list", "version": "Current version: {version}",
    "release": "Release page", "close": "Close", "developer": "VoidToDoList developed by bohangyang",
    "description": "A minimal work to-do assistant", "email": "Email: ", "drawer_style": "Drawer button:",
    "drawer_standard": "Standard", "drawer_minimal": "Minimal", "edit_todo": "Edit Todo",
    "day_summary": "Daily Summary", "week_summary": "Weekly Summary", "month_summary": "Monthly Summary",
    "summary": "Summary", "summary_title": "Summary", "copy": "Copy", "no_tasks_in_period": "No tasks in this period",
    "summary_completed": "Completed on {date}: {text}",
    "summary_in_progress": "In progress: {text}",
    "summary_item_format": "{number}.{text}",
    "save_fail_settings": "Failed to save settings, please check disk/file permissions.",
    "save_fail_todos": "Failed to save todo data, recent changes may be lost.",
    "startup_fail": "Failed to modify Windows startup setting.",
    "already_running": "VoidToDoList is already running.",
    "copy_with_ai": "Add AI prompt when copying",
    "edit_prompt": "Edit prompt",
    "prompt_created": "Default prompt created. You can click \"Edit prompt\" to modify it.",
    "copy_success": "Copy successful",
    "custom_summary": "Custom Summary", "custom_summary_title": "Select Date Range",
    "start_date": "From:", "end_date": "To:",
    "invalid_date_range": "Start date cannot be later than end date.",
    "invalid_date_text": "Please enter a valid date in the format shown above.",
    "date_after_today": "Cannot predict the future.",
    "retention": "Auto-delete:",
    "retention_2m": "2 months", "retention_6m": "6 months", "retention_1y": "1 year",
    "retention_2y": "2 years", "retention_5y": "5 years", "retention_never": "Never",
    "height_adjust": "Height adjustment:",
    "height_adjust_enable": "Allow", "height_adjust_disable": "Disable"
}
LANGUAGE_CATALOG = load_language_catalog()
LANGUAGE_CATALOG["en"] = {"code": "en", "name": "English", "direction": "ltr", "translations": BUILTIN_EN}
LANGUAGES = [(package.get("name", code), code) for code, package in LANGUAGE_CATALOG.items()]
TRANSLATIONS = {code: package["translations"] for code, package in LANGUAGE_CATALOG.items()}
# RTL codes are derived from each shipped package's declared direction, so a
# dangling hard-coded code (e.g. 'he' with no actual package) can never flip the
# UI into a wrongly-reversed layout.
RTL_LANGUAGES = {code for code, package in LANGUAGE_CATALOG.items() if package.get("direction") == "rtl"}


class CompletionButton(QPushButton):
    """Transparent completion control drawn consistently at any DPI."""
    def __init__(self, completed, scale=1.0):
        super().__init__()
        self.completed = completed
        self.scale = scale
        self.setFixedSize(round(42 * scale), round(42 * scale))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: rgba(255,255,255,30); } QPushButton:pressed { background: rgba(255,255,255,50); }")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("white"))
        offset, size = round(12 * self.scale), round(17 * self.scale)
        painter.drawRect(offset, offset, size, size)
        if self.completed:
            painter.drawLine(round(15 * self.scale), round(15 * self.scale), round(26 * self.scale), round(26 * self.scale))
            painter.drawLine(round(26 * self.scale), round(15 * self.scale), round(15 * self.scale), round(26 * self.scale))


class DoubleClickableLabel(QLabel):
    """A QLabel that emits a signal when double-clicked, used for inline todo text editing trigger."""
    def __init__(self, text, index, edit_callback, parent=None):
        super().__init__(text, parent)
        self._index = index
        self._edit_callback = edit_callback
        self.setWordWrap(True)
        self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self._edit_callback(self._index)


class TodoRow(QFrame):
    """A task row that grows to fit wrapped text."""
    def __init__(self, scale=1.0):
        super().__init__()
        self.scale = scale
        self._label = None
        self.setMinimumHeight(round(46 * scale))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def set_text_label(self, label):
        self._label = label
        QTimer.singleShot(0, self.update_height)

    def update_height(self):
        if self._label is None or self._label.width() <= 0 or self.layout() is None:
            return
        text_height = self._label.heightForWidth(self._label.width())
        margins = self.layout().contentsMargins()
        self.setMinimumHeight(max(round(46 * self.scale), text_height + margins.top() + margins.bottom()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.update_height)


class TodoDesktop(QWidget):
    """Desktop to-do panel, settings, and persistent task storage."""

    # Shared base stylesheet for all white dialogs (settings, about, summary, edit, etc.).
    _DIALOG_BASE_STYLE = (
        "QDialog { background: white; color: black; }"
        "QLabel { color: black; }"
        "QPushButton { color: black; background: #f2f2f2; border: 1px solid #b8b8b8; padding: 5px 16px; min-width: 80px; }"
        "QPushButton:hover { background: #e5e5e5; }"
    )

    def __init__(self):
        super().__init__()
        settings = read_json(SETTINGS_FILE, {})
        self.language = settings.get("language", "en")
        if self.language not in TRANSLATIONS: self.language = "en"
        self.display_mode = "drawer" if settings.get("display_mode") == "drawer" else "fixed"
        self.opacity = settings.get("opacity", 5)
        if self.opacity not in (5, 25, 50, 75, 95): self.opacity = 5
        self.drawer_style = "minimal" if settings.get("drawer_style") == "minimal" else "standard"
        self.copy_with_ai = settings.get("copy_with_ai", False)
        # Retention applies to the archive file only.  A pre-retention settings
        # file has no key, so it is treated as the new default and written back.
        self.retention = settings.get("retention", DEFAULT_RETENTION)
        if self.retention not in RETENTION_OPTIONS:
            self.retention = DEFAULT_RETENTION
        self._retention_needs_write = settings.get("retention") != self.retention
        self.height_adjust_enabled = bool(settings.get("height_adjust_enabled", False))
        self.window_height = max(settings.get("window_height", HEIGHT), MIN_HEIGHT)
        self._persisted = {"language": self.language, "display_mode": self.display_mode, "opacity": self.opacity, "drawer_style": self.drawer_style, "copy_with_ai": self.copy_with_ai, "retention": self.retention, "height_adjust_enabled": self.height_adjust_enabled, "window_height": self.window_height}
        self.ui_scale = screen_ui_scale()
        QApplication.instance().setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        # Initialize state flags before load_todos() runs, because the save path
        # it triggers reads them.
        self._allow_close = False
        self._persist_error = False   # becomes True if any save failed silently
        self._drawer_open = False      # authoritative intent state for the drawer
        if self._retention_needs_write:
            # Old settings file: persist the default retention before loading so
            # the pruning rules below and on the next launch agree.
            self.save_settings()
            self._retention_needs_write = False
        self.todos = self.load_todos()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._resizing = False
        self._resize_start_global_y = 0
        self._resize_start_height = 0
        self.apply_height_constraints()
        self.build_ui()
        self.apply_text_direction()
        self.apply_opacity_styles()
        self.position_window()
        # Daily (midnight-crossing) cleanup so done tasks do not linger stale until next reboot.
        self._midnight_timer = QTimer(self)
        self._midnight_timer.timeout.connect(self.purge_old_done_tasks)
        self._midnight_timer.start(30 * 60 * 1000)  # every 30 minutes
        # Re-anchor when the primary screen set changes (monitor unplug/plug, res change).
        QApplication.instance().primaryScreenChanged.connect(self.on_primary_screen_changed)
        QApplication.instance().screenRemoved.connect(lambda _screen: self.on_primary_screen_changed())
        if self.display_mode == "drawer":
            self.setup_drawer_mode()
        else:
            self.hide_drawer_button()

    def _show_toast(self, message):
        """Show a brief auto-hiding toast label over the main window."""
        toast = QLabel(message, self)
        toast.setAlignment(Qt.AlignCenter)
        toast.setStyleSheet(
            "QLabel { background: rgba(40,40,40,230); color: white; font-size: 14px;"
            "padding: 14px 32px; border-radius: 10px; }"
        )
        toast.adjustSize()
        # Center over the main window.
        wx, wy = self.x(), self.y()
        ww, wh = self.width(), self.height()
        toast.move((ww - toast.width()) // 2, (wh - toast.height()) // 2)
        toast.raise_()
        toast.show()
        QTimer.singleShot(1500, toast.deleteLater)

    def save_settings(self):
        self._persisted.update(language=self.language, display_mode=self.display_mode, opacity=self.opacity, drawer_style=self.drawer_style, copy_with_ai=self.copy_with_ai, retention=self.retention, height_adjust_enabled=self.height_adjust_enabled, window_height=self.window_height)
        ok = atomic_write_json(SETTINGS_FILE, self._persisted)
        self._check_persist(ok, "save_fail_settings")

    def save_todos(self):
        ok = atomic_write_json(DATA_FILE, self.todos)
        self._check_persist(ok, "save_fail_todos")

    def _check_persist(self, ok, error_key):
        if ok:
            self._persist_error = False
        elif not self._persist_error:
            self._persist_error = True
            self._show_toast(self.tr(error_key))

    def apply_height_constraints(self):
        """Drawer mode always shows the saved height; only the drag handle is
        gated by `height_adjust_enabled`.  Fixed mode always uses the default
        height, and the saved value is kept for returning to drawer mode."""
        width = round(WIDTH * self.ui_scale)
        drawer = self.display_mode == "drawer"
        height = round((self.window_height if drawer else MIN_HEIGHT) * self.ui_scale)
        self.setFixedWidth(width)
        if drawer and self.height_adjust_enabled:
            self.setMinimumHeight(round(MIN_HEIGHT * self.ui_scale))
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX (2^24 - 1): effectively no max
        else:
            self.setFixedHeight(height)
        self.resize(width, height)

    def set_height_adjust(self, enabled):
        """Enable/disable bottom-edge height adjustment; the saved height stays
        so it is restored when adjustment is re-enabled."""
        self.height_adjust_enabled = bool(enabled)
        self.apply_height_constraints()
        self.save_settings()

    # --- Bottom-edge drag-to-resize (height adjustment) ---
    def _resize_margin(self):
        return max(4, round(6 / self.ui_scale))

    def _on_bottom_edge(self, y):
        adjustable = self.height_adjust_enabled and self.display_mode == "drawer"
        return adjustable and y >= self.height() - self._resize_margin()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_bottom_edge(event.position().y()):
            self._resizing = True
            self._resize_start_global_y = event.globalPosition().y()
            self._resize_start_height = self.height()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.globalPosition().y() - self._resize_start_global_y
            new_height = round(self._resize_start_height + delta)
            min_height = round(MIN_HEIGHT * self.ui_scale)
            if new_height < min_height:
                new_height = min_height
            self.resize(self.width(), new_height)
            event.accept()
            return
        if self._on_bottom_edge(event.position().y()):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            self.window_height = round(self.height() / self.ui_scale)
            self.apply_height_constraints()
            self.save_settings()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not self._resizing:
            self.unsetCursor()
        super().leaveEvent(event)


    def tr(self, key):
        text = TRANSLATIONS.get(self.language, BUILTIN_EN).get(key, BUILTIN_EN.get(key, key))
        return text.replace("{version}", APP_VERSION)

    def set_language(self, code):
        # Update all currently visible surfaces immediately, including RTL mode.
        self.language = code
        self.save_settings()
        direction = Qt.RightToLeft if code in RTL_LANGUAGES else Qt.LeftToRight
        QApplication.instance().setLayoutDirection(direction)
        self.apply_text_direction()
        self.title_label.setText(self.tr("title"))
        self.entry.setPlaceholderText(self.tr("placeholder"))
        self.add_button.setToolTip(self.tr("add"))
        if hasattr(self, "drawer_button") and self.display_mode == "drawer":
            self.update_drawer_button(self._drawer_open)
            self.position_drawer_button()
        self.refresh_list()
        # A language change rebuilds every label, which can leave the open
        # settings dialog cramped or mis-measured.  Close and reopen it instead
        # so it always matches the new language's layout.  Deferred via a timer
        # because we are still inside the dialog's modal event loop here.
        if getattr(self, "_settings_dialog", None) is not None:
            self._reopen_settings_after_language_change()

    def _reopen_settings_after_language_change(self):
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is None:
            return
        self._settings_reopen_pending = True
        dialog.accept()

    def _maybe_reopen_settings(self):
        if getattr(self, "_settings_reopen_pending", False):
            self._settings_reopen_pending = False
            QTimer.singleShot(0, self.open_settings)

    def apply_text_direction(self):
        rtl = self.language in RTL_LANGUAGES
        direction = Qt.RightToLeft if rtl else Qt.LeftToRight
        alignment = Qt.AlignRight if rtl else Qt.AlignLeft
        self.setLayoutDirection(direction)
        self.title_label.setLayoutDirection(direction)
        self.title_label.setAlignment(alignment | Qt.AlignVCenter)
        self.entry.setLayoutDirection(direction)
        self.entry.setAlignment(alignment | Qt.AlignVCenter)
        self.add_button.setLayoutDirection(direction)
        if hasattr(self, "drawer_button"):
            self.drawer_button.setLayoutDirection(direction)
        for row_index in range(self.list_layout.count()):
            item = self.list_layout.itemAt(row_index)
            row = item.widget() if item else None
            if row is None or row.layout() is None:
                continue
            for child_index in range(row.layout().count()):
                child_item = row.layout().itemAt(child_index)
                child = child_item.widget() if child_item else None
                if isinstance(child, QLabel):
                    child.setLayoutDirection(direction)
                    child.setAlignment(alignment | Qt.AlignVCenter)

    def set_display_mode(self, mode):
        self.display_mode = mode
        self.save_settings()
        self.update_drawer_style_enabled()
        self.update_height_adjust_enabled()
        self.refit_settings_dialog()
        if mode == "drawer":
            self._drawer_open = False      # reset intent; setup starts collapsed
            self.setup_drawer_mode()
        else:
            self.hide_drawer_button()
            self.apply_height_constraints()
            self.show()
            self.position_window()

    def refit_settings_dialog(self):
        """Re-size an open settings dialog so newly shown/hidden rows fit."""
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is None:
            return
        layout = dialog.layout()
        if layout is not None:
            layout.activate()
        dialog.setFixedSize(dialog.sizeHint())

    def set_opacity(self, value):
        self.opacity = int(value)
        self.save_settings()
        self.apply_opacity_styles()

    def set_retention(self, value):
        """Persist the archive retention choice; it takes effect on the next prune."""
        self.retention = value if value in RETENTION_OPTIONS else DEFAULT_RETENTION
        self.save_settings()

    def align_settings_rows(self):
        """Line up every label/combo pair in one column.  Translated labels have
        different widths per language, so without this the dropdowns start at
        different x positions (visible with e.g. Russian)."""
        rows = getattr(self, "_settings_rows", None)
        if not rows:
            return
        label_width = max(label.sizeHint().width() for label, _combo in rows)
        combo_width = max(combo.sizeHint().width() for _label, combo in rows)
        for label, combo in rows:
            label.setFixedWidth(label_width)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            # A fixed combo width keeps the dropdowns the same size regardless
            # of whether the row is a bare layout or wrapped in a container.
            combo.setFixedWidth(combo_width)

    def set_drawer_style(self, style):
        self.drawer_style = "minimal" if style == "minimal" else "standard"
        self.save_settings()
        if hasattr(self, "drawer_button"):
            self.update_drawer_button(self._drawer_open)
            self.position_drawer_button()

    def update_drawer_style_enabled(self):
        if hasattr(self, "settings_drawer_style"):
            enabled = self.display_mode == "drawer"
            self.settings_drawer_style.setEnabled(enabled)
            self.settings_drawer_style_label.setEnabled(enabled)
            self.settings_drawer_style_row.setVisible(enabled)
            self.settings_drawer_style.setStyleSheet(
                "QComboBox:disabled { color: #888888; background: #eeeeee; }"
            )

    def update_height_adjust_enabled(self):
        if hasattr(self, "settings_height_adjust"):
            enabled = self.display_mode == "drawer"
            self.settings_height_adjust.setEnabled(enabled)
            self.settings_height_adjust_label.setEnabled(enabled)
            self.settings_height_adjust_row.setVisible(enabled)
            self.settings_height_adjust.setStyleSheet(
                "QComboBox:disabled { color: #888888; background: #eeeeee; }"
            )

    def apply_opacity_styles(self):
        alpha = round(255 * self.opacity / 100)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        text_color = "black" if self.opacity >= 60 else "white"
        self.entry.setStyleSheet(f"QLineEdit {{ background: rgba(255,255,255,{alpha}); border: none; color: {text_color}; padding: {max(3, round(8 * self.ui_scale))}px {max(4, round(10 * self.ui_scale))}px; }}")
        self.add_button.setStyleSheet(f"QPushButton {{ background: rgba(255,255,255,{alpha}); border: none; color: {text_color}; }} QPushButton:hover {{ background: rgba(255,255,255,{min(255, alpha + 12)}); }} QPushButton:pressed {{ background: rgba(255,255,255,{min(255, alpha + 20)}); }}")
        if hasattr(self, "drawer_button"):
            self.drawer_button.setStyleSheet(f"QPushButton {{ background: rgba(0,0,0,{alpha}); border: none; outline: none; color: white; padding: 0; margin: 0; }} QPushButton:hover {{ background: rgba(0,0,0,{alpha}); }}")
        self.update()

    def hide_drawer_button(self):
        """Ensure fixed mode never leaves a drawer control visible or animating."""
        for name in ("drawer_button_animation", "drawer_animation"):
            animation = getattr(self, name, None)
            if animation is not None:
                animation.stop()
        button = getattr(self, "drawer_button", None)
        if button is not None:
            button.hide()

    def setup_drawer_mode(self):
        if self.display_mode != "drawer":
            self.hide_drawer_button()
            return
        self.hide()
        if not hasattr(self, "drawer_button"):
            self.drawer_button = QPushButton()
            self.drawer_button.clicked.connect(self.toggle_drawer)
            self.drawer_button.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
            self.drawer_button.setAttribute(Qt.WA_TranslucentBackground, True)
            drawer_font = QFont(self.font())
            drawer_font.setFamilies(['Microsoft YaHei UI'])
            drawer_font.setPointSizeF(max(8.0, 15.0 * self.ui_scale))
            self.drawer_button.setFont(drawer_font)
            self.drawer_button.setCursor(Qt.PointingHandCursor)
            # 95% transparent black means only about 5% opacity (alpha 13).
            self.drawer_button.setStyleSheet("QPushButton { background: rgba(0,0,0,13); border: none; outline: none; color: white; padding: 0; margin: 0; } QPushButton:hover { background: rgba(0,0,0,13); }")
        self.update_drawer_button(False)
        self.apply_height_constraints()
        self.apply_opacity_styles()
        self.drawer_button.show()
        self.position_drawer_button()

    def drawer_hidden_x(self, screen):
        return screen.right() + 1

    def drawer_visible_x(self, screen):
        return screen.right() - self.width() + 1

    def drawer_button_x(self, panel_x):
        return panel_x - self.drawer_button.width()

    def position_drawer_button(self):
        screen = QApplication.primaryScreen().availableGeometry()
        panel_x = self.x() if self.isVisible() else self.drawer_hidden_x(screen)
        self.drawer_button.move(self.drawer_button_x(panel_x), screen.top())

    def update_drawer_button(self, expanded):
        if self.drawer_style == "minimal":
            text = ">>" if expanded else "<<"
        else:
            text = self.tr("drawer_close" if expanded else "drawer_open")
            text = f"   {text}   "
        self.drawer_button.setText(text)
        width = (round(42 * self.ui_scale) if self.drawer_style == "minimal"
                 else QFontMetrics(self.drawer_button.font()).horizontalAdvance(text) + round(20 * self.ui_scale))
        self.drawer_button.setFixedSize(width, round(42 * self.ui_scale))

    def current_screen(self):
        return QApplication.primaryScreen().availableGeometry()

    def toggle_drawer(self):
        # Intent-based rather than visibility-based so a click in the middle of
        # an animation correctly reverses the open/close direction.
        self.set_drawer_target(not self._drawer_open)

    def set_drawer_target(self, target_open):
        self._drawer_open = bool(target_open)
        self.update_drawer_button(self._drawer_open)
        screen = self.current_screen()
        if self._drawer_open:
            # Opening: if currently off/out of view, start from the hidden edge.
            if not self.isVisible():
                hidden = self.drawer_hidden_x(screen)
                if self.x() != hidden:
                    self.move(hidden, screen.top())
                self.show()
            self.animate_drawer_from_to(self.x(), self.drawer_visible_x(screen))
        else:
            self.animate_drawer_from_to(self.x(), self.drawer_hidden_x(screen), hide_after=True)

    def animate_drawer_from_to(self, start_x, end_x, hide_after=False):
        # Stop and detach any still-running animations first so multiple
        # concurrent animations never race on the same pos property and so a
        # stale `finished -> hide` connection can never hide a freshly opened
        # panel.  The libpyside backend emits a harmless RuntimeWarning when
        # disconnect() is called on a signal that has no connections, so the
        # call is wrapped in catch_warnings() in addition to try/except.
        for attr in ("drawer_animation", "drawer_button_animation"):
            anim = getattr(self, attr, None)
            if anim is not None:
                anim.stop()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    try:
                        anim.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
        screen = self.current_screen()
        self.move(start_x, screen.top())
        self.drawer_animation = QPropertyAnimation(self, b"pos", self)
        self.drawer_animation.setDuration(700)
        self.drawer_animation.setStartValue(QPoint(start_x, self.y()))
        self.drawer_animation.setEndValue(QPoint(end_x, self.y()))
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        if hide_after:
            self.drawer_animation.finished.connect(self._finish_drawer_collapse)

        self.position_drawer_button_for(start_x)
        self.drawer_button_animation = QPropertyAnimation(self.drawer_button, b"pos", self)
        self.drawer_button_animation.setDuration(700)
        self.drawer_button_animation.setStartValue(QPoint(self.drawer_button_x(start_x), self.y()))
        self.drawer_button_animation.setEndValue(QPoint(self.drawer_button_x(end_x), self.y()))
        self.drawer_button_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.drawer_animation.start()
        self.drawer_button_animation.start()

    def position_drawer_button_for(self, panel_x):
        self.drawer_button.move(self.drawer_button_x(panel_x), self.current_screen().top())

    def _finish_drawer_collapse(self):
        # Snap to the exact hidden edge then hide so no residual pixels drift
        # remain and so re-open from a known state.
        screen = self.current_screen()
        self.move(self.drawer_hidden_x(screen), screen.top())
        self.hide()

    def on_primary_screen_changed(self, _screen=None):
        # Re-anchor the panel and drawer edge after monitor plug/unplug or a
        # resolution change instead of leaving them parked off an old screen.
        screen = self.current_screen()
        if self.display_mode == "drawer":
            self.position_drawer_button_for(self.x())
            if not self._drawer_open:
                self.move(self.drawer_hidden_x(screen), screen.top())
            else:
                self.move(self.drawer_visible_x(screen), screen.top())
        else:
            self.position_window()

    def archive_done_tasks(self, tasks, today):
        """Remove cross-day done tasks into an append-only archive file.

        Missing `done_date` (legacy records) is treated as done-today so an
        in-place upgrade never silently deletes historical completions.
        """
        removed = []
        kept = []
        for todo in tasks:
            if not todo.get("done"):
                kept.append(todo)
                continue
            if todo.get("done_date") is None:
                # Legacy record with no completion date: keep it visible today.
                kept.append(todo)
                continue
            if todo.get("done_date") == today:
                kept.append(todo)
            else:
                removed.append(todo)
        if removed:
            try:
                archive_dir = os.path.dirname(DATA_FILE)
                archive_path = os.path.join(archive_dir, "todos.archive.json")
                existing = read_json(archive_path, [])
                if not isinstance(existing, list):
                    existing = []
                existing.extend(removed)
                atomic_write_json(archive_path, existing)
            except OSError:
                pass
        return kept

    def purge_old_done_tasks(self):
        """Daily cleanup invoked by a timer so done tasks do not linger stale
        across midnight until a restart."""
        before = len(self.todos)
        self.todos = self.archive_done_tasks(self.todos, date.today().isoformat())
        if len(self.todos) != before:
            self.save_todos()
            self.refresh_list()

    def load_todos(self):
        """Load todos, archive cross-day completions, and clean old archives."""
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as source:
                todos = json.load(source)
            if not isinstance(todos, list):
                todos = []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            todos = []
        today = date.today().isoformat()
        # Split: keep today's done + all in-progress, archive the rest.
        kept = []
        to_archive = []
        for todo in todos:
            if not todo.get("done"):
                kept.append(todo)
                continue
            if todo.get("done_date") is None or todo.get("done_date") == today:
                kept.append(todo)
            else:
                to_archive.append(todo)
        self.todos = kept
        # Merge new archive entries with existing archive, then prune old ones.
        archive_path = os.path.join(os.path.dirname(DATA_FILE), "todos.archive.json")
        archive = read_json(archive_path, [])
        if not isinstance(archive, list):
            archive = []
        archive.extend(to_archive)
        # "never" keeps every archived record, so the file is not rewritten at all.
        retention_days = RETENTION_DAYS.get(self.retention, RETENTION_DAYS[DEFAULT_RETENTION])
        if retention_days is None:
            pruned = archive
        else:
            cutoff = date.today() - timedelta(days=retention_days)
            pruned = []
            for t in archive:
                done_str = t.get("done_date")
                if done_str is None:
                    pruned.append(t)
                    continue
                try:
                    if date.fromisoformat(done_str) >= cutoff:
                        pruned.append(t)
                except (ValueError, TypeError):
                    pruned.append(t)
        if to_archive or (retention_days is not None and len(pruned) < len(archive)):
            atomic_write_json(archive_path, pruned)
        if to_archive:
            self.save_todos()
        return self.todos

    def build_ui(self):
        # The main window is transparent; only the input field has a visible fill.
        self.setStyleSheet("""
            QWidget { color: white; font-family: 'Microsoft YaHei UI'; }
            QLineEdit { background: rgba(255,255,255,26); border: none; color: white; }
            QLineEdit:focus { background: rgba(255,255,255,38); }
            QScrollArea, QScrollArea::viewport { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 5px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,45); min-height: 25px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        outer = QVBoxLayout(self)
        s = self.ui_scale
        outer.setContentsMargins(*(round(v * s) for v in (22, 22, 22, 22)))
        outer.setSpacing(round(12 * s))
        title = QLabel(self.tr("title"))
        title_font = QFont(title.font())
        title_font.setPointSizeF(max(8.0, 16.0 * s))
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title.setStyleSheet("background: transparent;")
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
        self.list_layout.setSpacing(round(8 * s))
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.list_widget)
        outer.addWidget(self.scroll, 1)
        add_row = QHBoxLayout()
        add_row.setSpacing(round(8 * s))
        self.entry = QLineEdit()
        self.entry.setPlaceholderText(self.tr("placeholder"))
        self.entry.setMinimumHeight(round(42 * s))
        entry_font = QFont(self.entry.font())
        entry_font.setPointSizeF(max(8.0, 12.0 * s))
        self.entry.setFont(entry_font)
        self.entry.setStyleSheet(f"QLineEdit {{ background: rgba(255,255,255,26); border: none; color: white; padding: {max(3, round(8 * s))}px {max(4, round(10 * s))}px; }}")
        self.entry.returnPressed.connect(self.add_todo)
        add_row.addWidget(self.entry, 1)
        add_button = self.action_button("+", round(48 * s))
        add_button.setToolTip(self.tr("add"))
        add_button.clicked.connect(self.add_todo)
        add_button.setContextMenuPolicy(Qt.CustomContextMenu)
        add_button.customContextMenuRequested.connect(self.show_summary_menu)
        self.add_button = add_button
        add_row.addWidget(add_button)
        outer.addLayout(add_row)
        self.refresh_list()

    def action_button(self, text, width, transparent=False):
        button = QPushButton(text)
        button.setFixedSize(width, round(42 * self.ui_scale))
        button.setCursor(Qt.PointingHandCursor)
        background = "transparent" if transparent else "rgba(255,255,255,26)"
        button_font = QFont(button.font())
        button_font.setPointSizeF(max(8.0, 20.0 * self.ui_scale))
        button.setFont(button_font)
        button.setStyleSheet(f"QPushButton {{ background: {background}; border: none; color: white; }} QPushButton:hover {{ background: rgba(255,255,255,30); }} QPushButton:pressed {{ background: rgba(255,255,255,50); }}")
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
            self.apply_text_direction()
            return
        for index, todo in enumerate(self.todos):
            row = TodoRow(self.ui_scale)
            row.setStyleSheet("background: transparent; border: none;")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(*(round(v * self.ui_scale) for v in (8, 2, 3, 2)))
            layout.setSpacing(round(6 * self.ui_scale))
            check = CompletionButton(todo.get("done", False), self.ui_scale)
            check.setToolTip(self.tr("done"))
            check.clicked.connect(lambda _checked=False, i=index: self.toggle_done(i))
            layout.addWidget(check)
            label = DoubleClickableLabel(todo.get("text", ""), index, self.open_edit_dialog)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label_font = QFont(label.font())
            label_font.setPointSizeF(max(8.0, 12.0 * self.ui_scale))
            label.setFont(label_font)
            label.setStyleSheet("color: rgba(255,255,255,145); text-decoration: line-through;" if todo.get("done") else "color: white;")
            layout.addWidget(label, 1)
            row.set_text_label(label)
            remove = self.action_button("×", 42, transparent=True)
            remove.setToolTip(self.tr("delete"))
            remove.clicked.connect(lambda _checked=False, i=index: self.delete_todo(i))
            layout.addWidget(remove)
            self.list_layout.addWidget(row)
        self.apply_text_direction()

    def add_todo(self):
        text = self.entry.text().strip()
        if text:
            self.todos.append({"text": text, "done": False, "done_date": None, "created_at": date.today().isoformat()})
            self.entry.clear()
            self.save_todos()
            self.refresh_list()

    def show_summary_menu(self, pos):
        """Right-click context menu on the + button."""
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        menu.setStyleSheet("QMenu { font-family: 'Microsoft YaHei UI'; color: black; background: white; } QMenu::item:selected { background: #e5e5e5; color: black; }")
        
        # Summary submenu
        summary_menu = menu.addMenu(self.tr("summary"))
        summary_menu.addAction(self.tr("day_summary"), lambda: self.open_summary_dialog("day"))
        summary_menu.addAction(self.tr("week_summary"), lambda: self.open_summary_dialog("week"))
        summary_menu.addAction(self.tr("month_summary"), lambda: self.open_summary_dialog("month"))
        summary_menu.addAction(self.tr("custom_summary"), self.open_custom_summary_dialog)
        
        menu.addSeparator()
        # App section
        menu.addAction(self.tr("settings"), self.open_settings)
        menu.addAction(self.tr("about"), self.open_about)
        menu.addSeparator()
        # Exit
        menu.addAction(self.tr("exit"), self.confirm_exit)
        menu.exec(self.add_button.mapToGlobal(pos))

    def all_recorded_todos(self):
        """Current list plus the archive, which is what every summary reads."""
        combined = list(self.todos)
        archive_path = os.path.join(os.path.dirname(DATA_FILE), "todos.archive.json")
        archive = read_json(archive_path, [])
        if isinstance(archive, list):
            combined.extend(archive)
        return combined

    def open_custom_summary_dialog(self):
        """Pick a date range, then reuse the standard summary window."""
        today = date.today()
        display_format = self.date_input_format()
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle("VoidToDoList " + self.tr("custom_summary_title"))
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        dialog.setStyleSheet(self._DIALOG_BASE_STYLE + """
            QLineEdit { color: black; background: white; padding: 4px; border: 1px solid #b8b8b8; }
            QPushButton { min-width: unset; padding: 4px 8px; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)
        # A grid keeps the two label/field rows aligned.  No space is reserved
        # for inline error text anymore, so a little extra vertical spacing
        # keeps the two rows comfortably separated.
        fields = QGridLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setHorizontalSpacing(round(8 * self.ui_scale))
        fields.setVerticalSpacing(round(14 * self.ui_scale))
        # Both labels share the width of this language's longer label, so they end
        # at the same edge and each gap to its field is equal and minimal.
        label_metrics = QFontMetrics(self.font())
        label_width = max(label_metrics.horizontalAdvance(self.tr("start_date")),
                          label_metrics.horizontalAdvance(self.tr("end_date")))
        start_editor = self._date_input_editor(fields, 0, "start_date", today, display_format, label_width)
        end_editor = self._date_input_editor(fields, 1, "end_date", today, display_format, label_width)
        # The label/field pair hugs the leading edge; the button row below is
        # centered, and neither row is stretched.  Pinning the label column keeps
        # the 8px gap to the field even when a wider dialog is needed for buttons.
        fields.setColumnStretch(0, 0)
        fields.setColumnStretch(1, 0)
        fields.setColumnMinimumWidth(0, label_width)
        fields_row = QHBoxLayout()
        fields_row.setContentsMargins(0, 0, 0, 0)
        fields_row.addLayout(fields)
        fields_row.addStretch(1)
        layout.addLayout(fields_row)
        confirm_button = QPushButton(self.tr("confirm"))
        cancel_button = QPushButton(self.tr("cancel"))
        confirm_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        # Confirm and cancel sit centered, in reading order per language.
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(round(8 * self.ui_scale))
        button_row.addStretch(1)
        for button in ((confirm_button, cancel_button) if self.language not in RTL_LANGUAGES
                       else (cancel_button, confirm_button)):
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        # Validation feedback is shown as an auto-hiding toast exactly like the
        # copy-success notification, so no fixed space is reserved for errors.
        toast_label = QLabel("", dialog)
        toast_label.setAlignment(Qt.AlignCenter)
        toast_label.setStyleSheet("QLabel { background: rgba(40,40,40,230); color: white; font-size: 16px; padding: 20px 40px; border-radius: 10px; }")
        toast_label.adjustSize()
        toast_label.setVisible(False)
        # Width is the larger of the two rows, so a language with long button
        # labels widens the dialog instead of eliding its buttons.
        margin = layout.contentsMargins()
        border = round(8 * self.ui_scale)
        field_width = round(150 * self.ui_scale)
        confirm_button.ensurePolished()
        cancel_button.ensurePolished()
        button_width = max(confirm_button.sizeHint().width(), cancel_button.sizeHint().width())
        fields_width = margin.left() + label_width + fields.horizontalSpacing() + field_width + border
        buttons_width = button_width * 2 + button_row.spacing() + margin.left() + margin.right()
        dialog.setFixedWidth(max(fields_width, buttons_width))
        dialog.setFixedHeight(dialog.sizeHint().height())
        for button in (confirm_button, cancel_button):
            button.setFixedWidth(button_width)

        while dialog.exec() == QDialog.Accepted:
            start = self._parse_date_input(start_editor.text())
            end = self._parse_date_input(end_editor.text())
            if start is None or end is None:
                self._show_dialog_toast(dialog, toast_label, self.tr("invalid_date_text"))
                continue
            if start > today or end > today:
                self._show_dialog_toast(dialog, toast_label, self.tr("date_after_today"))
                continue
            if start > end:
                self._show_dialog_toast(dialog, toast_label, self.tr("invalid_date_range"))
                continue
            self.open_summary_dialog("custom", start=start, end=end)
            return

    def date_input_format(self):
        """Conventional typed-date pattern for the active language, 4-digit year.

        Qt's own locale patterns use two-digit years and ambiguous day/month
        order, so each language gets an explicit, unambiguous year-first or
        day-first pattern instead.
        """
        return DATE_INPUT_FORMATS.get(self.language, DATE_INPUT_FORMATS["en"])

    def _date_input_editor(self, layout, row, label_key, initial, display_format, label_width):
        """Add one label + text field pair to a grid row.

        Returns the field.
        """
        label = QLabel(self.tr(label_key))
        label.setFixedWidth(label_width)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter if self.language not in RTL_LANGUAGES else Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(label, row, 0)
        editor = QLineEdit(initial.strftime(display_format))
        editor.setPlaceholderText(initial.strftime(display_format))
        editor.setFixedWidth(round(150 * self.ui_scale))
        layout.addWidget(editor, row, 1)
        return editor

    def _parse_date_input(self, text):
        """Parse a typed date, accepting the displayed pattern plus tolerant extras."""
        cleaned = text.strip().replace("\u200f", "").replace("\u200e", "")
        if not cleaned:
            return None
        # Any of these separators may stand in for each other.
        for separator in ("\u5e74", "\u6708", "\u65e5", "-", "/", ".", " "):
            cleaned = cleaned.replace(separator, "-")
        cleaned = cleaned.replace("\u53f7", "")
        # Drop a trailing marker such as the Chinese "日" turned into "-".
        cleaned = cleaned.strip("-")
        parts = [piece for piece in cleaned.split("-") if piece]
        if len(parts) != 3 or not all(piece.isdigit() for piece in parts):
            return None
        numbers = [int(piece) for piece in parts]
        order = DATE_INPUT_ORDER.get(self.language, "ymd")
        if order == "ymd":
            year, month, day = numbers
        elif order == "dmy":
            day, month, year = numbers
        else:
            month, day, year = numbers
        if year < 100:
            # Two-digit years are read as 2000s, which is the only sane range here.
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def add_button_row(self, layout, action_buttons, close_button):
        """Add a dialog button row: close on the right for LTR languages and on
        the left for RTL ones, with action buttons on the opposite side.

        Qt mirrors an HBoxLayout for RTL by itself, so ordering the widgets in
        the intended LTR sequence is enough in both cases:
        [actions..., close, stretch] puts the pair on the start edge, and a lone
        close needs [stretch, close] to sit on the end edge.
        """
        row = QHBoxLayout()
        row.setSpacing(8)
        if action_buttons:
            for button in action_buttons:
                row.addWidget(button)
            row.addWidget(close_button)
            row.addStretch()
        else:
            row.addStretch()
            row.addWidget(close_button)
        layout.addLayout(row)
        return row

    def open_summary_dialog(self, period_type, start=None, end=None):
        """Open a dialog showing a summary of tasks for the given period."""
        summary_text = self._build_summary_text(period_type, start=start, end=end)
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle("VoidToDoList " + self.tr("summary_title"))
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        dialog.setStyleSheet(self._DIALOG_BASE_STYLE + """
            QLabel#link { color: #0563c1; text-decoration: underline; }
            QCheckBox { color: black; }
            QTextEdit { color: black; background: #fafafa; border: 1px solid #b8b8b8; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        text_edit = QTextEdit()
        text_edit.setPlainText(summary_text)
        text_edit.setReadOnly(True)
        text_edit.setMinimumSize(400, 300)
        layout.addWidget(text_edit)
        # Checkbox row: AI prompt toggle + edit link
        checkbox_row = QHBoxLayout()
        checkbox_row.setSpacing(8)
        copy_checkbox = QCheckBox(self.tr("copy_with_ai"))
        edit_link = QLabel()
        edit_link.setObjectName("link")
        edit_link.linkActivated.connect(lambda link: self._open_word_file())

        def update_edit_link_state(checked):
            """Enable/colour the edit link only when the checkbox is checked."""
            if checked:
                edit_link.setText(f'<a href="#" style="color: #0563c1; text-decoration: underline;">{self.tr("edit_prompt")}</a>')
                edit_link.setCursor(Qt.PointingHandCursor)
            else:
                disabled = self.tr("edit_prompt")
                edit_link.setText(f'<span style="color: #bbbbbb;">{disabled}</span>')
                edit_link.setCursor(Qt.ArrowCursor)

        def on_toggle(checked):
            self._on_copy_with_ai_toggled(checked)
            update_edit_link_state(checked)

        # Apply the persisted state first (harmless here: no connections yet).
        copy_checkbox.setChecked(self.copy_with_ai)
        # Consistency fix before wiring up toggled, so the internal uncheck
        # below does not run through _on_copy_with_ai_toggled / ensure logic.
        if self.copy_with_ai and not os.path.exists(WORD_FILE):
            self.copy_with_ai = False
            self.save_settings()
            copy_checkbox.setChecked(False)
        copy_checkbox.toggled.connect(on_toggle)
        update_edit_link_state(self.copy_with_ai)
        checkbox_row.addWidget(copy_checkbox)
        checkbox_row.addWidget(edit_link)
        checkbox_row.addStretch()
        layout.addLayout(checkbox_row)
        # Button row
        copy_button = QPushButton(self.tr("copy"))
        close_button = QPushButton(self.tr("close"))
        close_button.clicked.connect(dialog.accept)
        self.add_button_row(layout, [copy_button], close_button)
        # Toast overlay label (hidden by default, floats above the dialog)
        toast_label = QLabel(self.tr("copy_success"), dialog)
        toast_label.setAlignment(Qt.AlignCenter)
        toast_label.setStyleSheet("QLabel { background: rgba(40,40,40,230); color: white; font-size: 16px; padding: 20px 40px; border-radius: 10px; }")
        toast_label.adjustSize()
        toast_label.setVisible(False)
        copy_button.clicked.connect(lambda: self._copy_summary(summary_text, copy_checkbox, toast_label, dialog))
        dialog.exec()

    def _on_copy_with_ai_toggled(self, checked):
        """Handle the copy_with_ai checkbox toggle."""
        self.copy_with_ai = checked
        self.save_settings()
        if checked:
            self._ensure_word_file()

    def _ensure_word_file(self):
        """Check if word.ini exists; if not, create it with default prompt and notify."""
        if os.path.exists(WORD_FILE):
            return
        try:
            # 使用 UTF-8 with BOM 编码写入，确保 Windows 记事本等编辑器能正确识别
            with open(WORD_FILE, "w", encoding="utf-8-sig") as f:
                f.write(DEFAULT_AI_PROMPT)
            msg = QMessageBox(self)
            msg.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
            msg.setWindowIcon(QIcon())
            msg.setIcon(QMessageBox.NoIcon)
            msg.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
            msg.setWindowTitle("VoidToDoList")
            msg.setText(self.tr("prompt_created"))
            msg.setStyleSheet("QMessageBox { color: black; } QMessageBox QLabel { color: black; } QMessageBox QPushButton { color: black; min-width: 72px; }")
            close_btn = msg.addButton(self.tr("close"), QMessageBox.ActionRole)
            msg.setDefaultButton(close_btn)
            msg.exec()
        except OSError:
            pass

    def _open_word_file(self):
        """Open word.ini with the system default text editor (Notepad)."""
        self._ensure_word_file()
        try:
            os.startfile(WORD_FILE)
        except OSError:
            pass

    def _copy_summary(self, summary_text, checkbox, toast_label, parent_dialog):
        """Copy summary text to clipboard, optionally with AI prompt prepended.
        Throttled: a second click within 1.5s of the last one is ignored."""
        now = time.monotonic()
        last = getattr(self, "_last_copy_time", 0.0)
        if now - last < 1.5:
            return
        self._last_copy_time = now
        if checkbox.isChecked():
            try:
                # 尝试多种编码读取文件，优先考虑常见的中文编码
                encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "utf-16", "utf-16-le", "latin-1"]
                prompt = None
                for encoding in encodings:
                    try:
                        with open(WORD_FILE, "r", encoding=encoding) as f:
                            prompt = f.read()
                        # 验证内容是否主要是有效文本（而不是乱码）
                        # 检查是否有足够的中文字符或ASCII字符
                        if prompt:
                            # 统计中文字符和ASCII字符的比例
                            chinese_count = sum(1 for c in prompt if '\u4e00' <= c <= '\u9fff')
                            ascii_count = sum(1 for c in prompt if c.isascii() and c.isprintable())
                            total_chars = len(prompt)
                            
                            # 如果中文字符或ASCII字符超过30%，认为是有效文本
                            if total_chars > 0 and (chinese_count + ascii_count) / total_chars > 0.3:
                                break
                        prompt = None  # 无效内容，继续尝试其他编码
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                if prompt is None:
                    # 如果所有编码都失败，尝试用最常见的编码读取
                    with open(WORD_FILE, "rb") as f:
                        content = f.read()
                    # 尝试用GBK解码（最常见的中文编码）
                    try:
                        prompt = content.decode("gbk")
                    except:
                        try:
                            prompt = content.decode("gb18030")
                        except:
                            try:
                                prompt = content.decode("utf-8")
                            except:
                                prompt = content.decode("utf-8", errors="ignore")
                full_text = prompt + "\n" + summary_text
            except (OSError, FileNotFoundError):
                full_text = summary_text
        else:
            full_text = summary_text
        QApplication.clipboard().setText(full_text)
        self._show_dialog_toast(parent_dialog, toast_label, self.tr("copy_success"))

    def _show_dialog_toast(self, parent_dialog, toast_label, message):
        """Show an auto-hiding toast centered over a dialog (copy-success style).

        Long messages wrap and stay inside the dialog instead of reserving
        fixed space for inline error text.
        """
        toast_label.setText(message)
        dlg_geo = parent_dialog.geometry()
        max_width = max(160, dlg_geo.width() - 40)
        # sizeHint().width() depends on the current wordWrap state, so leaving
        # it as-is makes long messages alternate between wrapping and a single
        # line on successive calls.  Force wrapping off before measuring so the
        # decision is always based on the true single-line width.
        toast_label.setWordWrap(False)
        single_line_width = toast_label.sizeHint().width()
        if single_line_width > max_width:
            toast_label.setWordWrap(True)
            toast_label.setFixedWidth(max_width)
        else:
            toast_label.setFixedWidth(single_line_width)
        toast_label.adjustSize()
        # Center over the parent dialog
        cx = (dlg_geo.width() - toast_label.width()) // 2
        cy = (dlg_geo.height() - toast_label.height()) // 2
        toast_label.move(cx, cy)
        toast_label.raise_()
        toast_label.setVisible(True)
        QApplication.processEvents()
        QTimer.singleShot(1000, lambda: toast_label.setVisible(False))

    def _build_summary_text(self, period_type, start=None, end=None):
        """Build the summary text for day/week/month or an explicit custom range."""
        today = date.today()
        if period_type == "day":
            start = end = today
        elif period_type == "week":
            monday = today - timedelta(days=today.weekday())
            start = monday
            end = monday + timedelta(days=6)
        elif period_type == "month":
            start = today.replace(day=1)
            next_month = (start + timedelta(days=32)).replace(day=1)
            end = next_month - timedelta(days=1)
        elif period_type == "custom":
            if start is None or end is None or start > end:
                return self.tr("no_tasks_in_period")
        else:
            return self.tr("no_tasks_in_period")
        # Collect tasks from both current list and archive.
        all_todos = self.all_recorded_todos()
        lines = []
        completed_template = self.tr("summary_completed")
        in_progress_template = self.tr("summary_in_progress")
        item_template = self.tr("summary_item_format")
        for todo in all_todos:
            if todo.get("done"):
                done_str = todo.get("done_date")
                if done_str:
                    try:
                        done_date = date.fromisoformat(done_str)
                        if start <= done_date <= end:
                            lines.append(completed_template.format(date=done_str, text=todo.get('text', '')))
                    except (ValueError, TypeError):
                        pass
            else:
                # 未完成的任务无论创建时间如何，都包含在总结中
                lines.append(in_progress_template.format(text=todo.get('text', '')))
        if not lines:
            return self.tr("no_tasks_in_period")
        return "\n".join(item_template.format(number=i+1, text=line) for i, line in enumerate(lines))

    def toggle_done(self, index):
        if not (0 <= index < len(self.todos)):
            return
        checked = not self.todos[index]["done"]
        self.todos[index]["done"] = checked
        self.todos[index]["done_date"] = date.today().isoformat() if checked else None
        self.save_todos()
        self.refresh_list()

    def open_edit_dialog(self, index):
        if not (0 <= index < len(self.todos)):
            return
        current_text = self.todos[index].get("text", "")
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle(self.tr("edit_todo"))
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        dialog.setStyleSheet(self._DIALOG_BASE_STYLE + """
            QLineEdit { color: black; background: white; padding: 6px; border: 1px solid #b8b8b8; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        editor = QLineEdit()
        editor.setText(current_text)
        editor.selectAll()
        layout.addWidget(editor)
        ok_button = QPushButton(self.tr("confirm"))
        cancel_button = QPushButton(self.tr("cancel"))
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        self.add_button_row(layout, [ok_button], cancel_button)
        if dialog.exec() == QDialog.Accepted:
            new_text = editor.text().strip()
            if not new_text:
                # Empty text: remove the task with confirmation.
                del self.todos[index]
                self.save_todos()
                self.refresh_list()
            elif new_text != current_text.strip():
                self.todos[index]["text"] = new_text
                self.save_todos()
                self.refresh_list()

    def delete_todo(self, index):
        if not (0 <= index < len(self.todos)):
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        confirmation.setText(self.tr("delete_q"))
        confirmation.setWindowTitle("VoidToDoList")
        confirmation.setWindowIcon(QIcon())
        confirmation.setIcon(QMessageBox.NoIcon)
        confirmation.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        confirmation.setStyleSheet("QMessageBox { color: black; } QMessageBox QLabel { color: black; } QMessageBox QPushButton { color: black; min-width: 72px; }")
        confirmation.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        yes_btn = confirmation.button(QMessageBox.Yes)
        if yes_btn:
            yes_btn.setText(self.tr("confirm"))
        no_btn = confirmation.button(QMessageBox.No)
        if no_btn:
            no_btn.setText(self.tr("cancel"))
        confirmation.setDefaultButton(QMessageBox.No)
        if confirmation.exec() != QMessageBox.Yes:
            return
        del self.todos[index]
        self.save_todos()
        self.refresh_list()

    def current_window_height(self):
        """Height in logical units the window should currently use.  Drawer mode
        keeps the saved height whether or not dragging is allowed; fixed mode
        always uses the default height."""
        if self.display_mode == "drawer":
            return self.window_height
        return MIN_HEIGHT

    def position_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        width, height = WIDTH * self.ui_scale, self.current_window_height() * self.ui_scale
        self.move(screen.x() + int(screen.width() * .75 - width / 2), screen.y() + int(screen.height() * .5 - height / 2))

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
        QMessageBox.warning(self, "VoidToDoList", self.tr("startup_fail"))

    def open_settings(self):
        # Settings are deliberately modal so a language change is immediately visible.
        dialog = QDialog(self)
        self._settings_dialog = dialog
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle("VoidToDoList")
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        dialog.setStyleSheet(self._DIALOG_BASE_STYLE + """
            QLabel, QCheckBox { color: black; }
            QComboBox { color: black; background: white; min-width: 150px; padding: 4px; }
            QComboBox QAbstractItemView { color: black; background: white; selection-color: black; selection-background-color: #e5e5e5; }
            QPushButton { min-width: unset; }
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
        self._settings_rows = [(language_label, language)]
        mode_row = QHBoxLayout()
        mode_label = QLabel(self.tr("mode"))
        self.settings_mode_label = mode_label
        mode_row.addWidget(mode_label)
        mode = QComboBox()
        mode.addItems([self.tr("fixed"), self.tr("drawer")])
        mode.setCurrentIndex(1 if self.display_mode == "drawer" else 0)
        mode.currentIndexChanged.connect(lambda index: self.set_display_mode("drawer" if index else "fixed"))
        self.settings_mode = mode
        mode_row.addWidget(mode)
        layout.addLayout(mode_row)
        self._settings_rows.append((mode_label, mode))
        drawer_style_row = QWidget()
        drawer_style_layout = QHBoxLayout(drawer_style_row)
        drawer_style_layout.setContentsMargins(0, 0, 0, 0)
        drawer_style_layout.setSpacing(12)
        drawer_style_label = QLabel(self.tr("drawer_style"))
        self.settings_drawer_style_label = drawer_style_label
        drawer_style_layout.addWidget(drawer_style_label)
        drawer_style = QComboBox()
        drawer_style.addItems([self.tr("drawer_standard"), self.tr("drawer_minimal")])
        drawer_style.setCurrentIndex(1 if self.drawer_style == "minimal" else 0)
        drawer_style.currentIndexChanged.connect(lambda index: self.set_drawer_style("minimal" if index else "standard"))
        self.settings_drawer_style = drawer_style
        drawer_style_layout.addWidget(drawer_style)
        self.settings_drawer_style_row = drawer_style_row
        layout.addWidget(drawer_style_row)
        self._settings_rows.append((drawer_style_label, drawer_style))
        self.update_drawer_style_enabled()
        height_adjust_row = QWidget()
        height_adjust_layout = QHBoxLayout(height_adjust_row)
        height_adjust_layout.setContentsMargins(0, 0, 0, 0)
        height_adjust_layout.setSpacing(12)
        height_adjust_label = QLabel(self.tr("height_adjust"))
        self.settings_height_adjust_label = height_adjust_label
        height_adjust_layout.addWidget(height_adjust_label)
        height_adjust = QComboBox()
        height_adjust.addItems([self.tr("height_adjust_enable"), self.tr("height_adjust_disable")])
        height_adjust.setCurrentIndex(0 if self.height_adjust_enabled else 1)
        height_adjust.currentIndexChanged.connect(lambda index: self.set_height_adjust(index == 0))
        self.settings_height_adjust = height_adjust
        height_adjust_layout.addWidget(height_adjust)
        self.settings_height_adjust_row = height_adjust_row
        layout.addWidget(height_adjust_row)
        self._settings_rows.append((height_adjust_label, height_adjust))
        self.update_height_adjust_enabled()
        opacity_row = QHBoxLayout()
        opacity_label = QLabel(self.tr("opacity"))
        self.settings_opacity_label = opacity_label
        opacity_row.addWidget(opacity_label)
        opacity = QComboBox()
        opacity_values = (5, 25, 50, 75, 95)
        opacity.addItems([f"{value}%" for value in opacity_values])
        opacity.setCurrentIndex(opacity_values.index(self.opacity))
        opacity.currentIndexChanged.connect(lambda index: self.set_opacity(opacity_values[index]))
        self.settings_opacity = opacity
        opacity_row.addWidget(opacity)
        layout.addLayout(opacity_row)
        self._settings_rows.append((opacity_label, opacity))
        retention_row = QHBoxLayout()
        retention_label = QLabel(self.tr("retention"))
        self.settings_retention_label = retention_label
        retention_row.addWidget(retention_label)
        retention = QComboBox()
        retention.addItems([self.tr(RETENTION_LABEL_KEYS[code]) for code in RETENTION_OPTIONS])
        retention.setCurrentIndex(RETENTION_OPTIONS.index(self.retention))
        retention.currentIndexChanged.connect(lambda index: self.set_retention(RETENTION_OPTIONS[index]))
        self.settings_retention = retention
        retention_row.addWidget(retention)
        layout.addLayout(retention_row)
        self._settings_rows.append((retention_label, retention))
        self.align_settings_rows()
        layout.addSpacing(6)
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
        self.add_button_row(layout, [], close_button)
        # Size the dialog to its own content.  The parent panel changes its own
        # height constraints between modes, and an unconstrained child dialog
        # would otherwise inherit an inflated size in drawer mode.
        self.refit_settings_dialog()
        dialog.finished.connect(lambda _result: self.clear_settings_refs())
        dialog.finished.connect(lambda _result: self._maybe_reopen_settings())
        dialog.exec()

    def clear_settings_refs(self):
        for name in ("settings_startup", "settings_language_label", "settings_mode_label", "settings_mode", "settings_drawer_style_row", "settings_drawer_style_label", "settings_drawer_style", "settings_height_adjust_row", "settings_height_adjust_label", "settings_height_adjust", "settings_opacity_label", "settings_opacity", "settings_retention_label", "settings_retention", "settings_version", "settings_release", "settings_close", "_settings_rows"):
            if hasattr(self, name):
                delattr(self, name)
        self._settings_dialog = None

    def open_about(self):
        # Keep the about dialog independent from the desktop panel styling.
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setWindowTitle("VoidToDoList")
        dialog.setWindowIcon(QIcon())
        dialog.setModal(True)
        dialog.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        dialog.setStyleSheet(self._DIALOG_BASE_STYLE)
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
        self.add_button_row(layout, [], close_button)
        dialog.exec()

    def confirm_exit(self):
        # Explicit cleanup is required because the main window ignores normal close events.
        confirmation = QMessageBox(self)
        confirmation.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        confirmation.setAttribute(Qt.WA_DeleteOnClose)
        confirmation.setIcon(QMessageBox.NoIcon)
        confirmation.setLayoutDirection(Qt.RightToLeft if self.language in RTL_LANGUAGES else Qt.LeftToRight)
        confirmation.setText(self.tr("exit_q"))
        confirmation.setWindowTitle("VoidToDoList")
        confirmation.setWindowIcon(QIcon())
        confirmation.setStyleSheet("QMessageBox { color: black; } QMessageBox QLabel { color: black; } QMessageBox QPushButton { color: black; min-width: 72px; }")
        confirmation.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        yes_btn = confirmation.button(QMessageBox.Yes)
        if yes_btn:
            yes_btn.setText(self.tr("confirm"))
        no_btn = confirmation.button(QMessageBox.No)
        if no_btn:
            no_btn.setText(self.tr("cancel"))
        confirmation.setDefaultButton(QMessageBox.No)
        if confirmation.exec() == QMessageBox.Yes:
            self.save_todos()
            self._allow_close = True
            self.hide()
            self.close()
            QApplication.instance().exit(0)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, round(255 * self.opacity / 100)))


def main():
    # Keep UI dimensions in logical pixels and let Qt scale them for Windows DPI.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Single-instance guard: prevents a second copy from running and clobbering
    # the same todos.json/settings.json (double-open data loss). The lock is
    # held for the process lifetime and released automatically on exit.
    single_lock = QLockFile(os.path.join(USER_DATA_DIR, "void.lock"))
    if not single_lock.tryLock(100):
        QMessageBox.information(None, "VoidToDoList", BUILTIN_EN["already_running"])
        return 0

    window = TodoDesktop()
    # TodoDesktop has already applied the persisted display mode.  Do not
    # unconditionally show the panel here, otherwise drawer mode is overridden.
    if window.display_mode == "fixed":
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
