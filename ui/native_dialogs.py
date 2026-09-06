"""Theme-aware desktop chrome/dialogs without creating a WebEngine instance."""
from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QWidget, QFileDialog, QDialog, QMessageBox, QInputDialog, QLabel

from utils.theme_manager import get_theme_manager


def dialog_parent(parent):
    """Use the owning top-level window, never a WebChannel QObject as QWidget."""
    current = parent
    while current is not None:
        if isinstance(current, QWidget):
            return current.window()
        try:
            current = current.parent()
        except (AttributeError, RuntimeError):
            break
    app = QApplication.instance()
    return QApplication.activeWindow() if isinstance(app, QApplication) else None


def start_directory(current: str) -> str:
    candidate = Path(str(current or '')).expanduser() if current else Path.home()
    try:
        while not candidate.is_dir() and candidate.parent != candidate:
            candidate = candidate.parent
        return str(candidate.resolve()) if candidate.is_dir() else str(Path.home())
    except (OSError, ValueError):
        return str(Path.home())


def select_directory(parent, title: str, current: str = '') -> str | None:
    """A themed, parented Qt picker; no Windows shell/native modal dependency."""
    app = QApplication.instance()
    if not isinstance(app, QApplication) or QThread.currentThread() is not app.thread():
        raise RuntimeError('폴더 선택은 앱의 UI 스레드에서 열어야 합니다')
    dialog = QFileDialog(dialog_parent(parent))
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setWindowTitle(str(title or '폴더 선택'))
    dialog.setDirectory(start_directory(current))
    dialog.setStyleSheet(get_theme_manager().get_stylesheet())
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    try:
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        selected = dialog.selectedFiles()
        return str(Path(selected[0]).resolve()) if selected and Path(selected[0]).is_dir() else None
    finally:
        dialog.deleteLater()


def apply_native_shell_theme(window, theme=None):
    theme = theme or get_theme_manager()
    background = theme.get_colors()['bg_primary']
    window.setStyleSheet(theme.get_stylesheet())
    stack = getattr(window, '_main_stack', None)
    if stack is not None:
        stack.setObjectName('aistudio_main_stack')
        # Scope to the stack itself: bare background rules recolor every button.
        stack.setStyleSheet(f'QStackedWidget#aistudio_main_stack {{ background: {background}; }}')
    viewer = getattr(window, 'vue_viewer', None)
    if viewer is not None:
        viewer.setObjectName('aistudio_vue_view')
        viewer.setStyleSheet(f'QWebEngineView#aistudio_vue_view {{ border: none; background: {background}; margin: 0; padding: 0; }}')
        viewer.page().setBackgroundColor(QColor(background))
    for name in ('web_tab', 'backend_ui_tab'):
        tab = getattr(window, name, None)
        if tab is not None and hasattr(tab, 'apply_theme'):
            tab.apply_theme()


class ThemedWebDialogs:
    """QWebEnginePage mixin: standard JS dialogs use the current native theme."""
    def _message_box(self, origin, message, *, confirm=False):
        box = QMessageBox(dialog_parent(self.parent()))
        host = origin.host() or 'AI Studio'
        box.setWindowTitle(f'{host} · ' + ('확인' if confirm else '알림'))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(str(message))
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel if confirm else QMessageBox.StandardButton.Ok)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel if confirm else QMessageBox.StandardButton.Ok)
        box.setEscapeButton(QMessageBox.StandardButton.Cancel if confirm else QMessageBox.StandardButton.Ok)
        box.button(QMessageBox.StandardButton.Ok).setText('확인')
        if confirm:
            box.button(QMessageBox.StandardButton.Cancel).setText('취소')
        box.setStyleSheet(get_theme_manager().get_stylesheet())
        try:
            return box.exec() == QMessageBox.StandardButton.Ok
        finally:
            box.deleteLater()

    def javaScriptAlert(self, security_origin, message):
        self._message_box(security_origin, message)

    def javaScriptConfirm(self, security_origin, message):
        return self._message_box(security_origin, message, confirm=True)

    def javaScriptPrompt(self, security_origin, message, default_value):
        dialog = QInputDialog(dialog_parent(self.parent()))
        dialog.setWindowTitle(f'{security_origin.host() or "AI Studio"} · 입력')
        dialog.setLabelText(str(message))
        for label in dialog.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setTextValue(default_value)
        dialog.setOkButtonText('확인')
        dialog.setCancelButtonText('취소')
        dialog.setStyleSheet(get_theme_manager().get_stylesheet())
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            return accepted, dialog.textValue() if accepted else ''
        finally:
            dialog.deleteLater()
