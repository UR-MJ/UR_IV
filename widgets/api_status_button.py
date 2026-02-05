# widgets/api_status_button.py
"""API 상태 표시 버튼 (애니메이션 포함)"""
import math
import random
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QFont


class _SandParticle:
    """떨어지는 모래 알갱이"""
    __slots__ = ('x', 'y', 'vy', 'size', 'alpha')

    def __init__(self, x: float, y: float):
        self.x = x + random.uniform(-0.8, 0.8)
        self.y = y
        self.vy = random.uniform(0.4, 1.0)
        self.size = random.uniform(0.8, 1.6)
        self.alpha = random.randint(160, 240)


class ApiStatusButton(QPushButton):
    """연결 상태에 따라 애니메이션이 변하는 API 관리 버튼"""

    STATE_IDLE = "idle"
    STATE_CONNECTING = "connecting"
    STATE_CONNECTED = "connected"
    STATE_FAILED = "failed"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        self._state = self.STATE_IDLE
        self._backend_name = "WebUI"
        self._label_text = "연결 대기"

        self._frame = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_tick)

        # 체크마크
        self._check_progress = 0.0
        self._pulse_phase = 0.0

        # 흔들림
        self._shake_offset = 0
        self._shake_count = 0

        # 모래시계
        self._sand_progress = 0.0
        self._hourglass_rotation = 0.0
        self._particles: list[_SandParticle] = []
        self._sand_pile_height = 0.0  # 아래에 쌓인 모래 높이 (0~1)

        # 배경
        self._bg_shift = 0.0

    # ── 공개 API ──

    def set_connecting(self, backend_name: str):
        """연결 중 상태 (모래시계 애니메이션)"""
        self._state = self.STATE_CONNECTING
        self._backend_name = backend_name
        self._label_text = f"{backend_name} 연결 중"
        self._frame = 0
        self._sand_progress = 0.0
        self._hourglass_rotation = 0.0
        self._particles.clear()
        self._sand_pile_height = 0.0
        self._bg_shift = 0.0
        self._anim_timer.start(33)  # ~30fps
        self.update()

    def set_connected(self, backend_name: str):
        """연결 성공 (체크마크 그리기)"""
        self._state = self.STATE_CONNECTED
        self._backend_name = backend_name
        self._label_text = f"{backend_name} 연결됨"
        self._frame = 0
        self._check_progress = 0.0
        self._pulse_phase = 0.0
        self._anim_timer.start(30)
        self.update()

    def set_failed(self, backend_name: str):
        """연결 실패 (흔들림)"""
        self._state = self.STATE_FAILED
        self._backend_name = backend_name
        self._label_text = f"{backend_name} 연결 실패"
        self._frame = 0
        self._shake_offset = 0
        self._shake_count = 0
        self._anim_timer.start(30)
        self.update()

    # ── 틱 ──

    def _on_tick(self):
        self._frame += 1
        if self._state == self.STATE_CONNECTING:
            self._tick_connecting()
        elif self._state == self.STATE_CONNECTED:
            self._tick_connected()
        elif self._state == self.STATE_FAILED:
            self._tick_failed()
        self.update()

    def _tick_connecting(self):
        """모래 떨어지기(40f) → 빠른 뒤집기(12f) → 반복"""
        cycle = 52
        phase = self._frame % cycle

        if phase < 40:
            # 모래 떨어지는 구간
            self._sand_progress = phase / 40.0
            self._hourglass_rotation = 0.0
            self._sand_pile_height = self._sand_progress

            # 파티클 생성 (매 프레임 1~2개)
            if self._sand_progress < 0.95:
                for _ in range(random.randint(1, 2)):
                    self._particles.append(_SandParticle(0, 0))
        else:
            # 빠른 뒤집기
            flip_t = (phase - 40) / 12.0
            # ease-in-out (가속→감속)
            ease = 0.5 - 0.5 * math.cos(flip_t * math.pi)
            self._hourglass_rotation = ease * 180.0
            self._sand_progress = 1.0
            self._particles.clear()
            self._sand_pile_height = 1.0 - flip_t  # 뒤집히면서 리셋

        # 파티클 물리
        alive = []
        for pt in self._particles:
            pt.y += pt.vy
            pt.vy += 0.12  # 중력
            pt.x += random.uniform(-0.15, 0.15)  # 미세 흔들림
            if pt.y < 14:  # 아래 삼각형 범위 내
                alive.append(pt)
        self._particles = alive

        self._bg_shift = (self._frame % 90) / 90.0

    def _tick_connected(self):
        if self._frame <= 20:
            self._check_progress = min(self._frame / 20.0, 1.0)
        else:
            self._check_progress = 1.0
            self._pulse_phase = ((self._frame - 20) % 60) / 60.0
        if self._frame > 120:
            self._anim_timer.stop()
            self._check_progress = 1.0
            self._pulse_phase = 0.0

    def _tick_failed(self):
        if self._shake_count < 6:
            amplitude = max(4.0 - self._shake_count * 0.6, 0.5)
            self._shake_offset = int(amplitude * math.sin(self._frame * 1.2))
            if self._frame % 5 == 0:
                self._shake_count += 1
        else:
            self._shake_offset = 0
            self._anim_timer.stop()

    # ── 그리기 ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._state == self.STATE_FAILED:
            p.translate(self._shake_offset, 0)

        self._draw_background(p, w, h)

        icon_rect = QRectF(4, 4, 30, h - 8)
        if self._state == self.STATE_CONNECTING:
            self._draw_hourglass(p, icon_rect)
        elif self._state == self.STATE_CONNECTED:
            self._draw_checkmark(p, icon_rect)
        elif self._state == self.STATE_FAILED:
            self._draw_x_mark(p, icon_rect)
        else:
            self._draw_dot(p, icon_rect)

        text_rect = QRectF(38, 0, w - 42, h)
        p.setPen(QColor(self._text_color()))
        p.setFont(self.font())
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._label_text)
        p.end()

    def _draw_background(self, p: QPainter, w: int, h: int):
        r = 6
        if self._state == self.STATE_CONNECTING:
            grad = QLinearGradient(self._bg_shift * w - w * 0.3, 0,
                                   self._bg_shift * w + w * 0.7, h)
            grad.setColorAt(0, QColor(70, 70, 30))
            grad.setColorAt(0.5, QColor(90, 85, 35))
            grad.setColorAt(1, QColor(70, 70, 30))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(140, 140, 60), 1))
        elif self._state == self.STATE_CONNECTED:
            pulse = math.sin(self._pulse_phase * math.pi * 2) * 0.15 if self._pulse_phase else 0
            base_g = int(90 + pulse * 60)
            p.setBrush(QColor(35, min(base_g, 120), 35))
            p.setPen(QPen(QColor(70, 180, 70), 1))
        elif self._state == self.STATE_FAILED:
            p.setBrush(QColor(80, 35, 35))
            p.setPen(QPen(QColor(180, 70, 70), 1))
        else:
            p.setBrush(QColor(50, 50, 50))
            p.setPen(QPen(QColor(80, 80, 80), 1))
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

    def _draw_hourglass(self, p: QPainter, rect: QRectF):
        """모래시계: 유리 + 모래 + 파티클"""
        cx, cy = rect.center().x(), rect.center().y()
        sz = min(rect.width(), rect.height()) * 0.42

        p.save()
        p.translate(cx, cy)
        p.rotate(self._hourglass_rotation)

        top = -sz
        bot = sz
        hw = sz * 0.7

        # ── 유리 외형 ──
        glass_pen = QPen(QColor(255, 225, 130), 1.8)
        p.setPen(glass_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # 상단 뚜껑
        p.drawLine(QPointF(-hw - 1, top), QPointF(hw + 1, top))
        # 하단 뚜껑
        p.drawLine(QPointF(-hw - 1, bot), QPointF(hw + 1, bot))
        # 왼쪽 곡선 (위→가운데→아래)
        for i in range(20):
            t1 = i / 20.0
            t2 = (i + 1) / 20.0
            x1 = -hw * (1 - 2 * abs(t1 - 0.5))
            y1 = top + (bot - top) * t1
            x2 = -hw * (1 - 2 * abs(t2 - 0.5))
            y2 = top + (bot - top) * t2
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        # 오른쪽 곡선
        for i in range(20):
            t1 = i / 20.0
            t2 = (i + 1) / 20.0
            x1 = hw * (1 - 2 * abs(t1 - 0.5))
            y1 = top + (bot - top) * t1
            x2 = hw * (1 - 2 * abs(t2 - 0.5))
            y2 = top + (bot - top) * t2
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── 위쪽 모래 (줄어듦) ──
        sand_remain = max(0.0, 1.0 - self._sand_progress)
        if sand_remain > 0.02:
            # 위쪽 삼각 영역의 모래 수위
            fill_h = sand_remain * (sz * 0.8)
            fill_y = -fill_h * 0.1  # 가운데 근처에서 시작
            # 모래 상단 Y (위쪽에서 아래로)
            sand_top_y = -fill_h
            # 해당 Y에서의 삼각 폭
            ratio = (sand_top_y - top) / (0 - top)  # 0~1
            sand_w = hw * max(ratio, 0) * 0.85

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(240, 195, 70, 210))
            pts = []
            # 모래 윗면 (약간 곡선처럼 여러 점)
            steps = 8
            for i in range(steps + 1):
                frac = i / steps
                px = -sand_w + 2 * sand_w * frac
                # 살짝 볼록한 아치
                arch = math.sin(frac * math.pi) * 0.8
                py = sand_top_y - arch
                pts.append(QPointF(px, py))
            # 아래쪽은 목 부분 (가운데)
            pts.append(QPointF(0.5, 0))
            pts.append(QPointF(-0.5, 0))
            p.drawPolygon(pts)

        # ── 아래쪽 모래 (쌓임) ──
        pile = self._sand_pile_height
        if pile > 0.02:
            fill_h = pile * (sz * 0.8)
            # 아래 삼각형: 바닥에서 위로 쌓임
            sand_bot_top = bot - fill_h
            ratio = (bot - sand_bot_top) / sz
            sand_w = hw * min(ratio, 1.0) * 0.85

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(240, 195, 70, 210))
            pts = [QPointF(-sand_w, sand_bot_top)]
            # 산봉우리 모양 (가운데가 볼록)
            steps = 10
            for i in range(steps + 1):
                frac = i / steps
                px = -sand_w + 2 * sand_w * frac
                # 산 모양
                mound = math.sin(frac * math.pi) * fill_h * 0.25
                py = sand_bot_top - mound
                pts.append(QPointF(px, py))
            pts.append(QPointF(sand_w, sand_bot_top))
            # 아래 바닥 꼭짓점
            pts.append(QPointF(hw * 0.4, bot - 1))
            pts.append(QPointF(-hw * 0.4, bot - 1))
            p.drawPolygon(pts)

        # ── 떨어지는 모래줄기 (중앙 스트림) ──
        if 0.03 < self._sand_progress < 0.97 and self._hourglass_rotation < 5:
            # 메인 줄기
            stream_alpha = int(220 - 180 * abs(self._sand_progress - 0.5))
            p.setPen(QPen(QColor(240, 200, 80, stream_alpha), 1.5))
            p.drawLine(QPointF(0, -1), QPointF(0, sz * 0.4))

            # 가느다란 보조 줄기
            p.setPen(QPen(QColor(240, 200, 80, stream_alpha // 2), 0.7))
            p.drawLine(QPointF(-0.6, 0), QPointF(-0.3, sz * 0.3))
            p.drawLine(QPointF(0.6, 0), QPointF(0.3, sz * 0.35))

        # ── 파티클 (떨어지는 모래알) ──
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            p.setBrush(QColor(245, 210, 90, pt.alpha))
            p.drawEllipse(QPointF(pt.x, pt.y), pt.size, pt.size)

        p.restore()

    def _draw_checkmark(self, p: QPainter, rect: QRectF):
        cx, cy = rect.center().x(), rect.center().y()
        size = min(rect.width(), rect.height()) * 0.35

        glow = int(180 + 40 * math.sin(self._pulse_phase * math.pi * 2)) if self._pulse_phase else 180
        p.setPen(QPen(QColor(80, glow, 80), 1.5))
        p.setBrush(QColor(40, 100, 40, 80))
        p.drawEllipse(QPointF(cx, cy), size + 2, size + 2)

        p1 = QPointF(cx - size * 0.5, cy)
        p2 = QPointF(cx - size * 0.1, cy + size * 0.45)
        p3 = QPointF(cx + size * 0.55, cy - size * 0.4)
        pen = QPen(QColor(120, 255, 120), 2.2, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        prog = self._check_progress
        if prog <= 0.4:
            t = prog / 0.4
            end = QPointF(p1.x() + (p2.x() - p1.x()) * t,
                          p1.y() + (p2.y() - p1.y()) * t)
            p.drawLine(p1, end)
        else:
            p.drawLine(p1, p2)
            t = (prog - 0.4) / 0.6
            end = QPointF(p2.x() + (p3.x() - p2.x()) * t,
                          p2.y() + (p3.y() - p2.y()) * t)
            p.drawLine(p2, end)

    def _draw_x_mark(self, p: QPainter, rect: QRectF):
        cx, cy = rect.center().x(), rect.center().y()
        size = min(rect.width(), rect.height()) * 0.3
        p.setPen(QPen(QColor(180, 60, 60), 1.5))
        p.setBrush(QColor(120, 40, 40, 80))
        p.drawEllipse(QPointF(cx, cy), size + 2, size + 2)
        pen = QPen(QColor(255, 100, 100), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        s = size * 0.55
        p.drawLine(QPointF(cx - s, cy - s), QPointF(cx + s, cy + s))
        p.drawLine(QPointF(cx + s, cy - s), QPointF(cx - s, cy + s))

    def _draw_dot(self, p: QPainter, rect: QRectF):
        cx, cy = rect.center().x(), rect.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(120, 120, 120))
        p.drawEllipse(QPointF(cx, cy), 4, 4)

    def _text_color(self) -> str:
        if self._state == self.STATE_CONNECTING:
            return "#ffe08e"
        elif self._state == self.STATE_CONNECTED:
            return "#8eff8e"
        elif self._state == self.STATE_FAILED:
            return "#ff8e8e"
        return "#aaaaaa"
