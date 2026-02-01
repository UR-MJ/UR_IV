# widgets/batch_report_dialog.py
"""
배치 생성 완료 리포트 다이얼로그
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QFrame, QHBoxLayout
)
from PyQt6.QtCore import Qt


class BatchReportDialog(QDialog):
    """배치 생성 결과 리포트"""

    def __init__(self, report: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("배치 생성 완료")
        self.setMinimumWidth(380)
        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; color: #E0E0E0; }
            QLabel { background: transparent; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # 제목
        title = QLabel("배치 생성 완료")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFF;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        layout.addWidget(line)

        total = report.get('total', 0)
        success = report.get('success', 0)
        fail = report.get('fail', 0)
        elapsed = report.get('elapsed', 0.0)
        avg_time = report.get('avg_time', 0.0)

        # 총 생성 수
        layout.addWidget(self._stat_row("총 생성", f"{total}장"))
        layout.addWidget(self._stat_row("성공", f"{success}장", "#43B581"))
        if fail > 0:
            layout.addWidget(self._stat_row("실패", f"{fail}장", "#E74C3C"))

        # 시간
        mins, secs = divmod(int(elapsed), 60)
        elapsed_str = f"{mins}분 {secs}초" if mins > 0 else f"{secs}초"
        layout.addWidget(self._stat_row("소요 시간", elapsed_str))
        layout.addWidget(self._stat_row("평균 생성 시간", f"{avg_time:.1f}초"))

        # 닫기 버튼
        btn_close = QPushButton("확인")
        btn_close.setFixedHeight(38)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #5865F2; color: white;
                border-radius: 6px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #4752C4; }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _stat_row(self, label: str, value: str, color: str = "#FFC107") -> QWidget:
        """통계 행 위젯"""
        row = QFrame()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #AAA; font-size: 14px;")
        h.addWidget(lbl)

        h.addStretch()

        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        h.addWidget(val)

        return row
