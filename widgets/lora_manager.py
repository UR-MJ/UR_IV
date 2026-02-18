# widgets/lora_manager.py
"""LoRA 브라우저 다이얼로그"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QSlider, QWidget,
    QApplication, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
import re


class LoraLoadWorker(QThread):
    """백엔드에서 LoRA 목록을 비동기로 로드"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, backend):
        super().__init__()
        self._backend = backend

    def run(self):
        try:
            if not self._backend:
                self.error.emit("백엔드가 없습니다.")
                return
            if not self._backend.test_connection():
                self.error.emit("백엔드 연결 실패 — 서버가 실행 중인지 확인하세요.")
                return
            loras = self._backend.get_loras()
            self.finished.emit(loras)
        except Exception as e:
            self.error.emit(str(e))


class LoraManagerDialog(QDialog):
    """LoRA 브라우저 다이얼로그"""
    lora_inserted = pyqtSignal(str)  # <lora:name:weight> 문자열
    loras_batch_inserted = pyqtSignal(str)  # 여러 <lora:...> 텍스트 일괄
    _lora_cache: list[dict] = []  # 클래스 레벨 캐시 (한 번 로드 후 재사용)

    def __init__(self, backend=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LoRA 관리자")
        self.setMinimumSize(500, 600)
        self.resize(550, 700)
        self.setStyleSheet("background-color: #1E1E1E; color: #EEE;")

        self._backend = backend
        self._all_loras: list[dict] = []
        self._worker: LoraLoadWorker | None = None

        self._setup_ui()

        # 캐시가 있으면 즉시 표시, 없으면 백엔드에서 로드
        if LoraManagerDialog._lora_cache:
            self._on_loaded(LoraManagerDialog._lora_cache)
        elif backend:
            self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 상단: 검색 + 새로고침
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("LoRA 검색...")
        self.search_input.setFixedHeight(35)
        self.search_input.setStyleSheet(
            "background-color: #2C2C2C; color: #EEE; border: 1px solid #555; "
            "border-radius: 4px; padding: 0 8px; font-size: 13px;"
        )
        self.search_input.textChanged.connect(self._filter_list)
        top_bar.addWidget(self.search_input)

        self.btn_refresh = QPushButton("새로고침")
        self.btn_refresh.setFixedHeight(35)
        self.btn_refresh.setStyleSheet(
            "background-color: #333; color: #DDD; border-radius: 4px; "
            "font-size: 12px; padding: 0 10px;"
        )
        self.btn_refresh.clicked.connect(self._refresh)
        top_bar.addWidget(self.btn_refresh)
        layout.addLayout(top_bar)

        # 목록
        self.lora_list = QListWidget()
        self.lora_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lora_list.setWordWrap(True)
        self.lora_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.lora_list.setStyleSheet(
            "QListWidget { background-color: #252525; border: 1px solid #444; "
            "border-radius: 4px; font-size: 12px; }"
            "QListWidget::item { padding: 6px 8px; }"
            "QListWidget::item:selected { background-color: #5865F2; }"
            "QListWidget::item:hover { background-color: #333; }"
        )
        layout.addWidget(self.lora_list, stretch=1)

        # 상태
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # 하단: 가중치 + 삽입 버튼
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        bottom.addWidget(QLabel("가중치:"))

        self.weight_slider = QSlider(Qt.Orientation.Horizontal)
        self.weight_slider.setRange(-500, 1000)
        self.weight_slider.setValue(80)
        self.weight_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #5865F2; width: 14px; margin: -4px 0; "
            "border-radius: 7px; }"
        )
        self.weight_slider.valueChanged.connect(self._update_weight_input)
        bottom.addWidget(self.weight_slider)

        self.weight_input = QLineEdit("0.80")
        self.weight_input.setFixedWidth(50)
        self.weight_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weight_input.setStyleSheet(
            "background-color: #2A2A2A; color: #DDD; border: 1px solid #444; "
            "border-radius: 3px; font-weight: bold; font-size: 12px;"
        )
        self.weight_input.editingFinished.connect(self._update_slider_from_input)
        bottom.addWidget(self.weight_input)

        self.btn_insert = QPushButton("삽입")
        self.btn_insert.setFixedSize(70, 35)
        self.btn_insert.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 4px; "
            "font-size: 13px; font-weight: bold;"
        )
        self.btn_insert.clicked.connect(self._on_insert)
        bottom.addWidget(self.btn_insert)

        layout.addLayout(bottom)

        # 텍스트 붙여넣기 영역
        paste_label = QLabel("텍스트로 일괄 추가:")
        paste_label.setStyleSheet("color: #AAA; font-size: 11px; margin-top: 4px;")
        layout.addWidget(paste_label)

        paste_row = QHBoxLayout()
        paste_row.setSpacing(6)

        self.paste_input = QTextEdit()
        self.paste_input.setFixedHeight(50)
        self.paste_input.setPlaceholderText("<lora:name1:0.8> <lora:name2:0.5> ...")
        self.paste_input.setStyleSheet(
            "background-color: #2C2C2C; color: #EEE; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px;"
        )
        paste_row.addWidget(self.paste_input)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        self.btn_clipboard = QPushButton("📋 붙여넣기")
        self.btn_clipboard.setFixedSize(80, 24)
        self.btn_clipboard.setStyleSheet(
            "background-color: #444; color: #DDD; border-radius: 3px; font-size: 12px;"
        )
        self.btn_clipboard.setToolTip("클립보드에서 붙여넣기")
        self.btn_clipboard.clicked.connect(self._fill_from_clipboard)
        btn_col.addWidget(self.btn_clipboard)

        self.btn_batch_insert = QPushButton("📥 일괄 추가")
        self.btn_batch_insert.setFixedSize(80, 24)
        self.btn_batch_insert.setStyleSheet(
            "background-color: #5865F2; color: white; border-radius: 3px; "
            "font-size: 12px; font-weight: bold;"
        )
        self.btn_batch_insert.clicked.connect(self._on_batch_insert)
        btn_col.addWidget(self.btn_batch_insert)

        paste_row.addLayout(btn_col)
        layout.addLayout(paste_row)

    def _update_weight_input(self, value: int):
        """슬라이더 → 입력 필드 동기화"""
        self.weight_input.setText(f"{value / 100:.2f}")

    def _update_slider_from_input(self):
        """입력 필드 → 슬라이더 동기화"""
        try:
            val = float(self.weight_input.text())
            val = max(-5.0, min(10.0, val))
            self.weight_slider.setValue(int(val * 100))
        except ValueError:
            pass

    def _refresh(self):
        """LoRA 목록 새로고침"""
        if not self._backend:
            self.status_label.setText("백엔드가 연결되지 않았습니다.")
            return

        self.status_label.setText("로딩 중...")
        self.lora_list.clear()

        self._worker = LoraLoadWorker(self._backend)
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_loaded(self, loras: list):
        LoraManagerDialog._lora_cache = loras  # 캐시 업데이트
        self._all_loras = loras
        self._populate_list(loras)
        self.status_label.setText(f"{len(loras)}개의 LoRA 발견 (캐시됨)")

    def _on_error(self, msg: str):
        self.status_label.setText(f"로드 실패: {msg}")

    def _populate_list(self, loras: list):
        self.lora_list.clear()
        for lora in loras:
            name = lora.get('name', '')
            alias = lora.get('alias', '')
            display = name if name == alias or not alias else f"{name} ({alias})"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.lora_list.addItem(item)

    def _filter_list(self, text: str):
        text_lower = text.lower()
        filtered = [
            l for l in self._all_loras
            if text_lower in l.get('name', '').lower()
            or text_lower in l.get('alias', '').lower()
        ]
        self._populate_list(filtered)

    def _fill_from_clipboard(self):
        """클립보드 내용을 텍스트 영역에 붙여넣기"""
        clipboard = QApplication.clipboard()
        if clipboard:
            text = clipboard.text().strip()
            if text:
                self.paste_input.setPlainText(text)

    def _on_batch_insert(self):
        """텍스트 영역에서 <lora:name:weight> 패턴 일괄 파싱 후 시그널 발사"""
        text = self.paste_input.toPlainText().strip()
        if not text:
            return
        pattern = re.compile(r'<lora:([^:>]+):(-?[\d.]+)>')
        matches = pattern.findall(text)
        if not matches:
            QMessageBox.information(
                self, "LoRA 붙여넣기",
                "유효한 <lora:name:weight> 패턴을 찾지 못했습니다.",
            )
            return
        self.loras_batch_inserted.emit(text)
        self.paste_input.clear()
        self.close()

    def _on_insert(self):
        item = self.lora_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        weight = self.weight_slider.value() / 100.0
        lora_text = f"<lora:{name}:{weight:.2f}>"
        self.lora_inserted.emit(lora_text)
        self.close()
