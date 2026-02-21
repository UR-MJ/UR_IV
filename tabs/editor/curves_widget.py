# tabs/editor/curves_widget.py
"""인터랙티브 커브 에디터 위젯"""
import numpy as np
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QButtonGroup
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
from utils.theme_manager import get_color


class CurvesWidget(QWidget):
    """인터랙티브 스플라인 커브 에디터 — RGB/R/G/B 채널별"""

    curve_changed = pyqtSignal()

    _CHANNEL_COLORS = {
        'rgb': QColor("#CCCCCC"),
        'r': QColor("#FF4444"),
        'g': QColor("#44CC44"),
        'b': QColor("#4488FF"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._channel = 'rgb'  # 현재 선택 채널
        # 각 채널별 제어점 [(x, y), ...] — 0~1 범위
        self._points = {
            'rgb': [(0.0, 0.0), (1.0, 1.0)],
            'r': [(0.0, 0.0), (1.0, 1.0)],
            'g': [(0.0, 0.0), (1.0, 1.0)],
            'b': [(0.0, 0.0), (1.0, 1.0)],
        }
        self._dragging_idx = -1
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 채널 선택 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._ch_group = QButtonGroup(self)

        _btn_style = """
            QPushButton {{{{
                background: {bg_button}; color: {{color}}; border: 1px solid {border};
                border-radius: 4px; font-size: 11px; font-weight: bold;
                padding: 3px 8px;
            }}}}
            QPushButton:checked {{{{
                background: {{bg}}; color: white; border: 1px solid {{color}};
            }}}}
        """.format(bg_button=get_color('bg_button'), border=get_color('border'))

        channels = [
            ('rgb', 'RGB', '#888', '#444'),
            ('r', 'R', '#F44', '#822'),
            ('g', 'G', '#4C4', '#282'),
            ('b', 'B', '#48F', '#248'),
        ]
        for i, (key, label, color, bg) in enumerate(channels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(_btn_style.format(color=color, bg=bg))
            self._ch_group.addButton(btn, i)
            btn_row.addWidget(btn)
        self._ch_group.button(0).setChecked(True)
        self._ch_group.buttonClicked.connect(
            lambda btn: self._set_channel(['rgb', 'r', 'g', 'b'][self._ch_group.id(btn)])
        )
        layout.addLayout(btn_row)

        # 커브 캔버스
        self._canvas = _CurveCanvas(self)
        self._canvas.setFixedHeight(180)
        layout.addWidget(self._canvas)

        # 초기화 버튼
        btn_reset = QPushButton("↩ 커브 초기화")
        btn_reset.setFixedHeight(28)
        btn_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_reset.setStyleSheet(
            f"background: {get_color('bg_button')}; color: {get_color('text_secondary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; font-size: 11px;"
        )
        btn_reset.clicked.connect(self._reset_current)
        layout.addWidget(btn_reset)

    def _set_channel(self, ch: str):
        self._channel = ch
        self._canvas.update()

    def _reset_current(self):
        """현재 채널 커브 초기화"""
        self._points[self._channel] = [(0.0, 0.0), (1.0, 1.0)]
        self._canvas.update()
        self.curve_changed.emit()

    def get_luts(self) -> tuple:
        """현재 커브를 채널별 256 LUT로 변환 — (lut_r, lut_g, lut_b)"""
        lut_r = self._build_lut('r')
        lut_g = self._build_lut('g')
        lut_b = self._build_lut('b')

        # RGB 통합 커브도 적용
        lut_rgb = self._build_lut('rgb')
        lut_r = lut_rgb[lut_r]
        lut_g = lut_rgb[lut_g]
        lut_b = lut_rgb[lut_b]

        return lut_r, lut_g, lut_b

    def _build_lut(self, channel: str) -> np.ndarray:
        """특정 채널의 제어점에서 256 LUT 생성"""
        pts = sorted(self._points[channel], key=lambda p: p[0])
        if len(pts) < 2:
            return np.arange(256, dtype=np.uint8)

        xs = np.array([p[0] for p in pts])
        ys = np.array([p[1] for p in pts])

        # 선형 보간 (단순하고 안정적)
        x_out = np.linspace(0, 1, 256)
        y_out = np.interp(x_out, xs, ys)
        y_out = np.clip(y_out * 255, 0, 255).astype(np.uint8)
        return y_out

    @staticmethod
    def apply_curves(img: np.ndarray, lut_r, lut_g, lut_b) -> np.ndarray:
        """커브 LUT를 이미지에 적용"""
        import cv2
        b, g, r = cv2.split(img)
        r = cv2.LUT(r, lut_r)
        g = cv2.LUT(g, lut_g)
        b = cv2.LUT(b, lut_b)
        return cv2.merge([b, g, r])

    def is_identity(self) -> bool:
        """모든 채널이 기본 (변경 없음)인지 확인"""
        for ch in ['rgb', 'r', 'g', 'b']:
            pts = self._points[ch]
            if len(pts) != 2:
                return False
            if pts[0] != (0.0, 0.0) or pts[1] != (1.0, 1.0):
                return False
        return True


class _CurveCanvas(QWidget):
    """커브 그리기 캔버스 (내부용)"""

    _HANDLE_R = 6
    _MARGIN = 10

    def __init__(self, parent: CurvesWidget):
        super().__init__(parent)
        self._curves = parent

    def _graph_rect(self):
        """그래프 영역 반환"""
        m = self._MARGIN
        return (m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _to_screen(self, pt: tuple) -> QPointF:
        gx, gy, gw, gh = self._graph_rect()
        return QPointF(gx + pt[0] * gw, gy + (1 - pt[1]) * gh)

    def _from_screen(self, pos) -> tuple:
        gx, gy, gw, gh = self._graph_rect()
        x = max(0, min(1, (pos.x() - gx) / gw))
        y = max(0, min(1, 1 - (pos.y() - gy) / gh))
        return (x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 배경
        painter.fillRect(self.rect(), QColor(get_color('bg_secondary')))

        gx, gy, gw, gh = self._graph_rect()

        # 격자
        painter.setPen(QPen(QColor(get_color('bg_button_hover')), 1))
        for i in range(1, 4):
            frac = i / 4.0
            x = int(gx + frac * gw)
            y = int(gy + frac * gh)
            painter.drawLine(x, gy, x, gy + gh)
            painter.drawLine(gx, y, gx + gw, y)

        # 대각선 (기본 커브)
        painter.setPen(QPen(QColor(get_color('border')), 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(gx), int(gy + gh), int(gx + gw), int(gy))

        # 현재 채널 커브
        ch = self._curves._channel
        pts = sorted(self._curves._points[ch], key=lambda p: p[0])
        color = CurvesWidget._CHANNEL_COLORS[ch]

        if len(pts) >= 2:
            # LUT로 커브 그리기
            lut = self._curves._build_lut(ch)
            path = QPainterPath()
            first = True
            for i in range(256):
                x = gx + (i / 255.0) * gw
                y = gy + (1 - lut[i] / 255.0) * gh
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # 제어점
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        for pt in pts:
            spt = self._to_screen(pt)
            painter.drawEllipse(spt, self._HANDLE_R, self._HANDLE_R)

        # 테두리
        painter.setPen(QPen(QColor(get_color('border')), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(gx, gy, gw, gh)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # 우클릭: 가장 가까운 제어점 삭제 (끝점 제외)
            ch = self._curves._channel
            pts = self._curves._points[ch]
            pos = QPointF(event.position())
            for i, pt in enumerate(pts):
                spt = self._to_screen(pt)
                if (pos - spt).manhattanLength() < self._HANDLE_R * 3:
                    # 첫점/끝점은 삭제 불가
                    sorted_pts = sorted(pts, key=lambda p: p[0])
                    if pt == sorted_pts[0] or pt == sorted_pts[-1]:
                        return
                    pts.remove(pt)
                    self.update()
                    self._curves.curve_changed.emit()
                    return
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        ch = self._curves._channel
        pts = self._curves._points[ch]
        pos = QPointF(event.position())

        # 기존 점 근처면 드래그 시작
        for i, pt in enumerate(pts):
            spt = self._to_screen(pt)
            if (pos - spt).manhattanLength() < self._HANDLE_R * 3:
                self._curves._dragging_idx = i
                return

        # 새 점 추가
        new_pt = self._from_screen(pos)
        pts.append(new_pt)
        pts.sort(key=lambda p: p[0])
        self._curves._dragging_idx = pts.index(new_pt)
        self.update()
        self._curves.curve_changed.emit()

    def mouseMoveEvent(self, event):
        idx = self._curves._dragging_idx
        if idx < 0:
            return
        ch = self._curves._channel
        pts = self._curves._points[ch]
        new_pt = self._from_screen(QPointF(event.position()))

        # 첫점/끝점은 x 고정
        sorted_pts = sorted(pts, key=lambda p: p[0])
        if pts[idx] == sorted_pts[0]:
            new_pt = (0.0, max(0, min(1, new_pt[1])))
        elif pts[idx] == sorted_pts[-1]:
            new_pt = (1.0, max(0, min(1, new_pt[1])))
        else:
            new_pt = (max(0, min(1, new_pt[0])), max(0, min(1, new_pt[1])))

        pts[idx] = new_pt
        self.update()
        self._curves.curve_changed.emit()

    def mouseReleaseEvent(self, event):
        self._curves._dragging_idx = -1
