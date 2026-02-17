# widgets/interactive_label.py
import cv2
import numpy as np
import time
from PyQt6.QtWidgets import QLabel, QSizePolicy, QApplication
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QPolygon, QTransform, QColor
from utils.shortcut_manager import get_shortcut_manager

class InteractiveLabel(QLabel):
    """모자이크 편집용 인터랙티브 라벨"""
    state_changed = pyqtSignal(bool, bool)
    wm_position_changed = pyqtSignal(float, float)  # x_pct, y_pct
    wm_scale_changed = pyqtSignal(float)             # scale ratio
    wm_resize_finished = pyqtSignal()                # 리사이즈 완료
    color_picked = pyqtSignal(tuple)                 # BGR 색상 (스포이트)

    def __init__(self, parent_editor):
        super().__init__()
        self.parent_editor = parent_editor
        
        self.cv_image = None            
        self.display_base_image = None 
        self.pristine_image = None      
        
        self.current_tool = 'box'
        self.brush_size = 20
        self.selection_mask = None
        self.eraser_restores_image = False 
        
        self.undo_stack = []
        self.redo_stack = []
        
        self.zoom_modifier = Qt.KeyboardModifier.ControlModifier
        self.rotate_modifier = Qt.KeyboardModifier.ShiftModifier
        self.rotation_angle = 0
        self.zoom_factor = 1.0
        
        self.pan_x = 0
        self.pan_y = 0
        self.is_panning = False
        self.drag_last_pos = None
        self.last_alt_press_time = 0
        
        self.start_pos = None
        self.end_pos = None
        self.lasso_path = []
        self.is_drawing = False
        self.cursor_pos = None
        self.last_draw_pos = None

        # Caps Lock 직선 모드 관련
        self._straight_line_anchor = None  # 직선 모드의 시작점

        # 자석 올가미 관련
        self.magnetic_lasso = False  # 자석 올가미 모드 on/off
        self._edge_map = None  # Canny 에지 맵 (캐시)
        self._edge_map_dirty = True

        # 워터마크 드래그 관련
        self._wm_overlay = None          # BGRA numpy 또는 None
        self._wm_mode = False            # 워터마크 드래그 모드
        self._wm_dragging = False
        self._wm_drag_offset = QPoint()  # 드래그 시작 시 커서-오버레이 오프셋
        self._wm_x_pct = 50.0            # 현재 위치 (% 0-100)
        self._wm_y_pct = 50.0
        self._wm_clamp = True            # 이미지 영역 내 제한
        self._wm_resizing = False        # 크기 조절 드래그
        self._wm_resize_start_dist = 0.0 # 리사이즈 시작 시 중심~커서 거리
        self._wm_resize_base_val = 0     # 리사이즈 시작 시 슬라이더 값

        # 그리기 모드
        self.draw_mode = False
        self.draw_tool = 'pen'
        self.draw_color = (0, 0, 0)  # BGR
        self.draw_size = 3
        self.draw_opacity = 1.0
        self.draw_filled = False
        self._draw_start = None      # 직선/도형 시작점 (이미지 좌표)
        self._draw_preview_end = None  # 미리보기 끝점 (이미지 좌표)
        self._draw_pen_active = False  # 펜 그리기 중

        # 클론 스탬프
        self._clone_source = None      # 소스 좌표 (이미지 좌표, tuple)
        self._clone_offset = None      # 소스↔대상 오프셋 (dx, dy)
        self._clone_active = False     # 클론 중

        # 이동 모드
        self.move_mode = False
        self._move_region = None       # BGR 이미지 조각
        self._move_mask = None         # uint8 마스크 조각
        self._move_offset_x = 0
        self._move_offset_y = 0
        self._move_origin_bbox = None  # (x, y, w, h)
        self._move_drag_start = None   # QPoint (화면 좌표)
        self._last_hole_mask = None    # 인페인트용
        self._move_rotation = 0        # 회전 각도 (도)
        self._move_scale = 1.0         # 크기 배율

        # 설정 가능한 파라미터 (설정 탭에서 변경 가능)
        self._snap_radius = 12
        self._canny_low = 50
        self._canny_high = 150
        self._smooth_factor = 0.008
        self._rotation_step = 5
        self._undo_limit = 20

        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, 
            QSizePolicy.Policy.Ignored
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.is_panning = False
        self.last_alt_press_time = 0        

    def set_modifiers(self, zoom_mod, rotate_mod):
        """키 수정자 설정"""
        self.zoom_modifier = zoom_mod
        self.rotate_modifier = rotate_mod
        
    def set_brush_size(self, size):
        """브러시 크기 설정"""
        self.brush_size = size
        self.update()

    def push_undo_stack(self):
        """Undo 스택에 현재 상태 저장"""
        if self.display_base_image is None: 
            return
        if len(self.undo_stack) >= self._undo_limit:
            self.undo_stack.pop(0)
        state = {
            'image': self.display_base_image.copy(),
            'mask': self.selection_mask.copy() if self.selection_mask is not None else None
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()
        self._emit_state_change()

    def undo(self):
        """실행 취소"""
        if not self.undo_stack: 
            return
        current_state = {
            'image': self.display_base_image.copy(),
            'mask': self.selection_mask.copy() if self.selection_mask is not None else None
        }
        self.redo_stack.append(current_state)
        prev_state = self.undo_stack.pop()
        self.display_base_image = prev_state['image']
        self.selection_mask = prev_state['mask']
        self.rotate_image(0)
        self._emit_state_change()

    def redo(self):
        """다시 실행"""
        if not self.redo_stack: 
            return
        current_state = {
            'image': self.display_base_image.copy(),
            'mask': self.selection_mask.copy() if self.selection_mask is not None else None
        }
        self.undo_stack.append(current_state)
        next_state = self.redo_stack.pop()
        self.display_base_image = next_state['image']
        self.selection_mask = next_state['mask']
        self.rotate_image(0)
        self._emit_state_change()

    def _emit_state_change(self):
        """상태 변경 시그널 발송"""
        self.state_changed.emit(len(self.undo_stack) > 0, len(self.redo_stack) > 0)

    def reset_view(self):
        """뷰 초기화"""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.rotation_angle = 0
        if self.display_base_image is not None:
            self.rotate_image(0)
        self.update()

    def set_image(self, cv_img):
        """이미지 설정"""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._emit_state_change()
        
        self.pristine_image = cv_img.copy()
        self.display_base_image = cv_img.copy()
        self.cv_image = cv_img.copy()
        self._edge_map_dirty = True
        self.reset_view() 
        
        if self.display_base_image is not None:
            h, w = self.display_base_image.shape[:2]
            self.selection_mask = np.zeros((h, w), dtype=np.uint8)
        else:
            self.selection_mask = None
        self.update()

    def update_image_keep_view(self, new_img):
        """뷰 유지하면서 이미지 업데이트"""
        self.display_base_image = new_img.copy()
        if self.pristine_image is None or self.pristine_image.shape != new_img.shape:
            self.pristine_image = new_img.copy()
        self.rotate_image(0) 
        
        if self.display_base_image is not None:
            h, w = self.display_base_image.shape[:2]
            if self.selection_mask is None or self.selection_mask.shape != (h, w):
                self.selection_mask = np.zeros((h, w), dtype=np.uint8)
        self.update()

    def set_tool(self, tool_name):
        """도구 설정"""
        self.current_tool = tool_name
        self.update()

    def set_draw_mode(self, enabled: bool):
        """그리기 모드 전환"""
        self.draw_mode = enabled
        self._draw_start = None
        self._draw_preview_end = None
        self._draw_pen_active = False
        self._clone_active = False
        self.update()

    def set_draw_params(self, tool: str, color: tuple, size: int,
                        opacity: float, filled: bool):
        """그리기 파라미터 설정"""
        self.draw_tool = tool
        self.draw_color = color
        self.draw_size = size
        self.draw_opacity = opacity
        self.draw_filled = filled
        self.update()

    def _draw_on_image(self, img, pt1, pt2, tool: str, color, size, opacity, filled):
        """이미지에 직접 그리기 (투명도 지원)"""
        if opacity >= 1.0:
            self._draw_primitive(img, pt1, pt2, tool, color, size, filled)
        else:
            overlay = img.copy()
            self._draw_primitive(overlay, pt1, pt2, tool, color, size, filled)
            cv2.addWeighted(overlay, opacity, img, 1.0 - opacity, 0, img)

    def _draw_primitive(self, img, pt1, pt2, tool: str, color, size, filled):
        """기본 도형 그리기"""
        thickness = size if not filled else -1
        if tool == 'pen':
            cv2.line(img, pt1, pt2, color, size, cv2.LINE_AA)
        elif tool == 'line':
            cv2.line(img, pt1, pt2, color, size, cv2.LINE_AA)
        elif tool == 'rect':
            x1, y1 = min(pt1[0], pt2[0]), min(pt1[1], pt2[1])
            x2, y2 = max(pt1[0], pt2[0]), max(pt1[1], pt2[1])
            if filled:
                cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
            else:
                cv2.rectangle(img, (x1, y1), (x2, y2), color, size)
        elif tool == 'ellipse':
            cx = (pt1[0] + pt2[0]) // 2
            cy = (pt1[1] + pt2[1]) // 2
            rx = abs(pt2[0] - pt1[0]) // 2
            ry = abs(pt2[1] - pt1[1]) // 2
            if rx > 0 and ry > 0:
                if filled:
                    cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, color, -1, cv2.LINE_AA)
                else:
                    cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, color, size, cv2.LINE_AA)

    def _flood_fill_at(self, pos):
        """채우기 도구"""
        if self.display_base_image is None:
            return
        bx, by = self.map_to_base_coordinates(pos)
        bx, by = int(round(bx)), int(round(by))
        h, w = self.display_base_image.shape[:2]
        if bx < 0 or by < 0 or bx >= w or by >= h:
            return
        self.push_undo_stack()
        if self.draw_opacity >= 1.0:
            mask = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(self.display_base_image, mask, (bx, by),
                          self.draw_color, (20, 20, 20), (20, 20, 20),
                          cv2.FLOODFILL_FIXED_RANGE)
        else:
            overlay = self.display_base_image.copy()
            mask = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(overlay, mask, (bx, by),
                          self.draw_color, (20, 20, 20), (20, 20, 20),
                          cv2.FLOODFILL_FIXED_RANGE)
            cv2.addWeighted(overlay, self.draw_opacity,
                            self.display_base_image, 1.0 - self.draw_opacity,
                            0, self.display_base_image)
        self.rotate_image(0)
        self.update()

    def _eyedropper_at(self, pos):
        """스포이트 도구"""
        if self.display_base_image is None:
            return
        bx, by = self.map_to_base_coordinates(pos)
        bx, by = int(round(bx)), int(round(by))
        h, w = self.display_base_image.shape[:2]
        if 0 <= bx < w and 0 <= by < h:
            bgr = tuple(int(c) for c in self.display_base_image[by, bx])
            self.color_picked.emit(bgr)

    def _apply_clone_at(self, dst_x: int, dst_y: int):
        """클론 스탬프: 소스→대상으로 원형 브러시 영역 복사"""
        if self.display_base_image is None or self._clone_offset is None:
            return
        img = self.display_base_image
        h, w = img.shape[:2]
        ox, oy = self._clone_offset
        src_x = dst_x + ox
        src_y = dst_y + oy
        r = max(1, self.draw_size // 2)

        # 경계 체크용 클립
        y1s = max(0, src_y - r); y2s = min(h, src_y + r)
        x1s = max(0, src_x - r); x2s = min(w, src_x + r)
        y1d = max(0, dst_y - r); y2d = min(h, dst_y + r)
        x1d = max(0, dst_x - r); x2d = min(w, dst_x + r)

        # 양쪽 모두 유효한 영역만
        oy1 = max(y1s - (src_y - r), y1d - (dst_y - r))
        ox1 = max(x1s - (src_x - r), x1d - (dst_x - r))
        oy2 = min(y2s - (src_y - r), y2d - (dst_y - r))
        ox2 = min(x2s - (src_x - r), x2d - (dst_x - r))

        if oy2 <= oy1 or ox2 <= ox1:
            return

        # 원형 마스크
        diameter = r * 2
        yy, xx = np.ogrid[:diameter, :diameter]
        circle = ((xx - r) ** 2 + (yy - r) ** 2) <= r * r
        mask_slice = circle[oy1:oy2, ox1:ox2]

        sy = src_y - r + oy1; sx = src_x - r + ox1
        dy = dst_y - r + oy1; dx = dst_x - r + ox1
        sh = oy2 - oy1; sw = ox2 - ox1

        src_patch = img[sy:sy + sh, sx:sx + sw].copy()
        dst_patch = img[dy:dy + sh, dx:dx + sw]

        alpha = self.draw_opacity
        if alpha >= 1.0:
            dst_patch[mask_slice] = src_patch[mask_slice]
        else:
            blended = cv2.addWeighted(src_patch, alpha, dst_patch, 1.0 - alpha, 0)
            dst_patch[mask_slice] = blended[mask_slice]

    # ── 이동 모드 ──

    def set_move_mode(self, enabled: bool):
        """이동 모드 전환"""
        self.move_mode = enabled
        if not enabled and self._move_region is not None:
            # 이동 중 탭 전환 시 취소
            self.cancel_move()
        self.update()

    def start_move(self, fill_color: tuple = (0, 0, 0)) -> bool:
        """선택 영역을 부유 상태로 분리"""
        if self.selection_mask is None or cv2.countNonZero(self.selection_mask) == 0:
            return False

        self.push_undo_stack()

        # bbox 계산
        coords = cv2.findNonZero(self.selection_mask)
        x, y, w, h = cv2.boundingRect(coords)
        self._move_origin_bbox = (x, y, w, h)

        # 영역 추출
        roi_mask = self.selection_mask[y:y+h, x:x+w].copy()
        roi_image = self.display_base_image[y:y+h, x:x+w].copy()
        self._move_region = roi_image
        self._move_mask = roi_mask

        # 인페인트용 구멍 마스크 저장
        self._last_hole_mask = self.selection_mask.copy()

        # 원래 자리를 채우기 색으로 채움
        self.display_base_image[self.selection_mask > 0] = fill_color

        # 선택 마스크 초기화
        self.selection_mask.fill(0)
        self._move_offset_x = 0
        self._move_offset_y = 0

        self.rotate_image(0)
        return True

    def confirm_move(self):
        """부유 영역을 현재 위치에 합성 (회전/크기 적용)"""
        if self._move_region is None or self._move_origin_bbox is None:
            return

        ox, oy, orig_w, orig_h = self._move_origin_bbox

        # 회전/크기 적용
        region = self._move_region.copy()
        mask = self._move_mask.copy()
        ms = self._move_scale
        mr = self._move_rotation

        if ms != 1.0:
            new_w = max(1, int(orig_w * ms))
            new_h = max(1, int(orig_h * ms))
            region = cv2.resize(region, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            mask = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
        else:
            new_w, new_h = orig_w, orig_h

        if mr != 0:
            center = (new_w // 2, new_h // 2)
            M = cv2.getRotationMatrix2D(center, mr, 1.0)
            cos_v = np.abs(M[0, 0])
            sin_v = np.abs(M[0, 1])
            rot_w = int(new_h * sin_v + new_w * cos_v)
            rot_h = int(new_h * cos_v + new_w * sin_v)
            M[0, 2] += (rot_w / 2) - center[0]
            M[1, 2] += (rot_h / 2) - center[1]
            region = cv2.warpAffine(region, M, (rot_w, rot_h),
                                    borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
            mask = cv2.warpAffine(mask, M, (rot_w, rot_h),
                                  flags=cv2.INTER_NEAREST,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            new_w, new_h = rot_w, rot_h

        nx = ox + self._move_offset_x
        ny = oy + self._move_offset_y
        img_h, img_w = self.display_base_image.shape[:2]

        # 소스/대상 영역 클리핑
        src_x1 = max(0, -nx)
        src_y1 = max(0, -ny)
        src_x2 = min(new_w, img_w - nx)
        src_y2 = min(new_h, img_h - ny)

        if src_x2 <= src_x1 or src_y2 <= src_y1:
            return

        dst_x1 = max(0, nx)
        dst_y1 = max(0, ny)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)

        region_slice = region[src_y1:src_y2, src_x1:src_x2]
        mask_slice = mask[src_y1:src_y2, src_x1:src_x2]

        dst_roi = self.display_base_image[dst_y1:dst_y2, dst_x1:dst_x2]
        dst_roi[mask_slice > 0] = region_slice[mask_slice > 0]

        # 상태 초기화 (hole mask는 유지)
        self._move_region = None
        self._move_mask = None
        self._move_origin_bbox = None
        self._move_drag_start = None

        self._edge_map_dirty = True
        self.rotate_image(0)

    def cancel_move(self):
        """이동 취소"""
        if self._move_region is not None:
            self.undo()
        self._move_region = None
        self._move_mask = None
        self._move_origin_bbox = None
        self._move_drag_start = None
        self._last_hole_mask = None
        self.update()

    def get_move_hole_mask(self):
        """마지막 이동의 구멍 마스크 반환"""
        if self._last_hole_mask is None:
            return None
        return self._last_hole_mask.copy()

    def clear_selection(self):
        """선택 영역 초기화"""
        if self.selection_mask is not None and cv2.countNonZero(self.selection_mask) > 0:
            self.push_undo_stack()
            self.selection_mask.fill(0)
            self.update()
        self.is_drawing = False
        self.lasso_path = []
        self.start_pos = None
        self.end_pos = None

    def get_current_mask(self):
        """현재 마스크 반환"""
        return self.selection_mask

    def rotate_image(self, angle):
        """이미지 회전"""
        if self.display_base_image is None: 
            return
        self.rotation_angle += angle
        old_scale, _, _ = self.get_scale_info()

        h, w = self.display_base_image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, self.rotation_angle, 1.0)
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        M[0, 2] += (new_w / 2) - center[0]
        M[1, 2] += (new_h / 2) - center[1]
        
        self.cv_image = cv2.warpAffine(self.display_base_image, M, (new_w, new_h))
        
        if self.width() > 0 and self.height() > 0:
            new_img_h, new_img_w = self.cv_image.shape[:2]
            new_base_scale = min(self.width() / new_img_w, self.height() / new_img_h)
            if new_base_scale > 0:
                self.zoom_factor = old_scale / new_base_scale
        self.update()

    def map_to_base_coordinates(self, screen_pos):
        """화면 좌표를 베이스 이미지 좌표로 변환"""
        rx, ry = self.screen_to_image(screen_pos)
        if self.display_base_image is None: 
            return rx, ry
        h, w = self.display_base_image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, self.rotation_angle, 1.0)
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        M[0, 2] += (new_w / 2) - center[0]
        M[1, 2] += (new_h / 2) - center[1]
        
        M_inv = cv2.invertAffineTransform(M)
        pt = np.array([[[rx, ry]]], dtype=np.float32)
        base_pt = cv2.transform(pt, M_inv)
        bx, by = base_pt[0][0]
        return bx, by

    # ──────────────────────────────────────────────────
    #  Caps Lock / 자석 올가미 / 떨림 보정
    # ──────────────────────────────────────────────────

    @staticmethod
    def _is_caps_lock_on() -> bool:
        """Caps Lock 상태 확인"""
        try:
            import ctypes
            return bool(ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1)
        except Exception:
            return False

    def _get_edge_map(self):
        """현재 이미지의 Canny 에지 맵 (캐시)"""
        if self._edge_map_dirty or self._edge_map is None:
            if self.display_base_image is not None:
                gray = cv2.cvtColor(self.display_base_image, cv2.COLOR_BGR2GRAY)
                blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                self._edge_map = cv2.Canny(blurred, self._canny_low, self._canny_high)
            else:
                self._edge_map = None
            self._edge_map_dirty = False
        return self._edge_map

    def _snap_to_edge(self, bx, by, search_radius=15):
        """에지 맵에서 가장 가까운 에지 포인트로 스냅"""
        edge_map = self._get_edge_map()
        if edge_map is None:
            return bx, by

        h, w = edge_map.shape
        ix, iy = int(round(bx)), int(round(by))

        # 검색 영역
        x1 = max(0, ix - search_radius)
        y1 = max(0, iy - search_radius)
        x2 = min(w, ix + search_radius + 1)
        y2 = min(h, iy + search_radius + 1)

        roi = edge_map[y1:y2, x1:x2]
        edge_pts = np.argwhere(roi > 0)  # (row, col) = (y, x)

        if len(edge_pts) == 0:
            return bx, by

        # 가장 가까운 에지 포인트 찾기
        dists = (edge_pts[:, 1] + x1 - ix) ** 2 + (edge_pts[:, 0] + y1 - iy) ** 2
        nearest = edge_pts[np.argmin(dists)]
        return float(nearest[1] + x1), float(nearest[0] + y1)

    def _smooth_lasso_path(self, screen_pts):
        """올가미 경로 떨림 보정 (Douglas-Peucker 단순화 + 스무딩)"""
        if len(screen_pts) < 5:
            return screen_pts

        pts = np.array(screen_pts, dtype=np.float32).reshape(-1, 1, 2)
        # 경로 길이에 비례하는 epsilon
        arc_len = cv2.arcLength(pts, closed=False)
        epsilon = max(1.0, arc_len * self._smooth_factor)
        simplified = cv2.approxPolyDP(pts, epsilon, closed=False)
        return simplified.reshape(-1, 2).tolist()

    def _snap_lasso_point(self, screen_pos):
        """올가미 포인트를 에지에 스냅 (자석 올가미)"""
        bx, by = self.map_to_base_coordinates(screen_pos)
        snapped_bx, snapped_by = self._snap_to_edge(bx, by, search_radius=self._snap_radius)

        # 스냅된 좌표를 다시 스크린 좌표로 변환하기는 복잡하므로
        # base 좌표 차이가 작으면 원래 screen_pos 반환 (시각적 차이 미미)
        dist = ((snapped_bx - bx) ** 2 + (snapped_by - by) ** 2) ** 0.5
        if dist < 1.0:
            return screen_pos

        # 에지에 스냅됐으면 원래 screen_pos에 스냅 오프셋을 반영
        scale, off_x, off_y = self.get_scale_info()
        dx = (snapped_bx - bx) * scale
        dy = (snapped_by - by) * scale
        return QPoint(int(screen_pos.x() + dx), int(screen_pos.y() + dy))

    def _stamp_bars_along_line(self, start_pos, end_pos):
        """Caps Lock 직선 모드: 시작점→끝점까지 간격마다 검은띠 스탬프"""
        if self.display_base_image is None:
            return

        dist_threshold = max(5, self.parent_editor.slider_strength.value())
        sx, sy = start_pos.x(), start_pos.y()
        ex, ey = end_pos.x(), end_pos.y()

        dx = ex - sx
        dy = ey - sy
        total_dist = np.sqrt(dx ** 2 + dy ** 2)

        if total_dist < 1:
            return

        self.push_undo_stack()

        # 간격 단위로 직선 위의 포인트 생성
        steps = max(1, int(total_dist / dist_threshold))
        for i in range(steps + 1):
            t = i / max(steps, 1)
            px = int(sx + dx * t)
            py = int(sy + dy * t)
            self._apply_paint_tool(QPoint(px, py), is_bar_censor=True)

    def _apply_paint_tool(self, pos, prev_pos=None, is_eraser=False, is_bar_censor=False):
        """페인트 도구 적용"""
        if self.display_base_image is None: 
            return
        
        bx, by = self.map_to_base_coordinates(pos)
        r = int(self.brush_size)
        
        if is_bar_censor:
            bar_w = self.parent_editor.slider_bar_w.value()
            bar_h = self.parent_editor.slider_bar_h.value()
            
            # 사각형 꼭짓점 정의
            rect_points = np.array([
                [bx - bar_w/2, by - bar_h/2],
                [bx + bar_w/2, by - bar_h/2],
                [bx + bar_w/2, by + bar_h/2],
                [bx - bar_w/2, by + bar_h/2]
            ], dtype=np.float32)

            # 회전 적용
            if self.rotation_angle != 0:
                M = cv2.getRotationMatrix2D((bx, by), -self.rotation_angle, 1.0) 
                rect_points = cv2.transform(np.array([rect_points]), M)[0]

            rect_points = np.round(rect_points).astype(np.int32)
            cv2.fillPoly(self.display_base_image, [rect_points], (0, 0, 0))
            
            self.rotate_image(0)
            return

        thickness = r * 2
        bx_int, by_int = int(round(bx)), int(round(by))
        
        if prev_pos is not None:
            pbx, pby = self.map_to_base_coordinates(prev_pos)
            pbx_int, pby_int = int(round(pbx)), int(round(pby))
            
            if is_eraser:
                if self.eraser_restores_image and self.pristine_image is not None:
                    temp_mask = np.zeros(
                        self.display_base_image.shape[:2], 
                        dtype=np.uint8
                    )
                    cv2.line(
                        temp_mask, (pbx_int, pby_int), (bx_int, by_int), 
                        255, thickness, cv2.LINE_AA
                    )
                    self.display_base_image[temp_mask > 0] = self.pristine_image[temp_mask > 0]
                    self.rotate_image(0)
                if self.selection_mask is not None:
                    cv2.line(
                        self.selection_mask, (pbx_int, pby_int), (bx_int, by_int), 
                        0, thickness, cv2.LINE_AA
                    )
            else:
                if self.selection_mask is not None:
                    cv2.line(
                        self.selection_mask, (pbx_int, pby_int), (bx_int, by_int), 
                        255, thickness, cv2.LINE_AA
                    )
        else:
            if is_eraser:
                if self.eraser_restores_image and self.pristine_image is not None:
                    temp_mask = np.zeros(
                        self.display_base_image.shape[:2], 
                        dtype=np.uint8
                    )
                    cv2.circle(temp_mask, (bx_int, by_int), r, 255, -1)
                    self.display_base_image[temp_mask > 0] = self.pristine_image[temp_mask > 0]
                    self.rotate_image(0)
                if self.selection_mask is not None:
                    cv2.circle(self.selection_mask, (bx_int, by_int), r, 0, -1)
            else:
                if self.selection_mask is not None:
                    cv2.circle(self.selection_mask, (bx_int, by_int), r, 255, -1)

    def wheelEvent(self, event):
        """마우스 휠 이벤트"""
        delta = event.angleDelta().y()
        modifiers = event.modifiers()
        
        if modifiers & self.zoom_modifier:
            if delta > 0: 
                self.zoom_factor *= 1.1
            else: 
                self.zoom_factor *= 0.9
            if self.zoom_factor < 0.1: 
                self.zoom_factor = 0.1
            self.update()
        elif modifiers & self.rotate_modifier:
            step = self._rotation_step if delta > 0 else -self._rotation_step
            self.rotate_image(step)
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        """키보드 이벤트"""
        sm = get_shortcut_manager()

        if sm.match(event, 'prev_image'):
            if hasattr(self.parent_editor, 'select_prev_image'):
                self.parent_editor.select_prev_image()
            return
        elif sm.match(event, 'next_image'):
            if hasattr(self.parent_editor, 'select_next_image'):
                self.parent_editor.select_next_image()
            return
        elif sm.match(event, 'delete_image'):
            if hasattr(self.parent_editor, 'delete_selected_image'):
                self.parent_editor.delete_selected_image()
            return
        elif sm.match(event, 'copy_image'):
            if hasattr(self.parent_editor, 'copy_image_to_clipboard'):
                self.parent_editor.copy_image_to_clipboard()
            return
        elif sm.match(event, 'pan_mode'):
            current_time = time.time()
            if current_time - self.last_alt_press_time < 0.3:
                self.reset_view()
            self.last_alt_press_time = current_time
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        super().keyPressEvent(event)                
            
    def keyReleaseEvent(self, event):
        """키 해제 이벤트"""
        sm = get_shortcut_manager()
        if sm.match(event, 'pan_mode'):
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().keyReleaseEvent(event)

    def get_scale_info(self):
        """스케일 정보 반환"""
        if self.cv_image is None: 
            return 1.0, 0, 0
        w_widget = self.width()
        h_widget = self.height()
        h_img, w_img = self.cv_image.shape[:2]
        if w_widget == 0 or h_widget == 0: 
            return 1.0, 0, 0
        base_scale = min(w_widget / w_img, h_widget / h_img)
        final_scale = base_scale * self.zoom_factor
        disp_w = int(w_img * final_scale)
        disp_h = int(h_img * final_scale)
        offset_x = ((w_widget - disp_w) // 2) + self.pan_x
        offset_y = ((h_widget - disp_h) // 2) + self.pan_y
        return final_scale, offset_x, offset_y

    # ── 워터마크 오버레이 ──

    def set_wm_mode(self, enabled: bool):
        """워터마크 드래그 모드 활성화/비활성화"""
        self._wm_mode = enabled
        if not enabled:
            self._wm_overlay = None
            self._wm_dragging = False
            self._wm_resizing = False
        self.update()

    def set_wm_clamp(self, clamp: bool):
        """워터마크 이미지 영역 제한 설정"""
        self._wm_clamp = clamp
        if clamp and self._wm_overlay is not None and self.cv_image is not None:
            self._apply_wm_clamp()
            self.wm_position_changed.emit(self._wm_x_pct, self._wm_y_pct)
            self.update()

    def set_wm_overlay(self, bgra: np.ndarray, x_pct: float, y_pct: float):
        """워터마크 미리보기 오버레이 설정 (BGRA numpy 배열)"""
        self._wm_overlay = bgra
        self._wm_x_pct = x_pct
        self._wm_y_pct = y_pct
        self.update()

    def clear_wm_overlay(self):
        """워터마크 오버레이 제거"""
        self._wm_overlay = None
        self.update()

    def _apply_wm_clamp(self):
        """워터마크 위치를 이미지 영역 내로 제한 (적용 시 _pct_to_xy와 동일한 정수 연산)"""
        if self._wm_overlay is None or self.cv_image is None:
            return
        h_img, w_img = self.cv_image.shape[:2]
        wm_h, wm_w = self._wm_overlay.shape[:2]
        # _pct_to_xy: x = int(w * pct/100) - wm_w//2  →  x >= 0  ⇒  pct >= wm_w//2 / w * 100
        #             x + wm_w <= w  ⇒  pct <= (w - wm_w + wm_w//2) / w * 100
        min_x_pct = (wm_w // 2) / w_img * 100.0
        max_x_pct = (w_img - wm_w + wm_w // 2) / w_img * 100.0
        min_y_pct = (wm_h // 2) / h_img * 100.0
        max_y_pct = (h_img - wm_h + wm_h // 2) / h_img * 100.0
        self._wm_x_pct = max(min_x_pct, min(max_x_pct, self._wm_x_pct))
        self._wm_y_pct = max(min_y_pct, min(max_y_pct, self._wm_y_pct))

    def _wm_screen_rect(self):
        """현재 워터마크 오버레이의 화면 좌표 QRect 반환"""
        if self._wm_overlay is None or self.cv_image is None:
            return None
        scale, off_x, off_y = self.get_scale_info()
        h_img, w_img = self.cv_image.shape[:2]
        wm_h, wm_w = self._wm_overlay.shape[:2]

        # 이미지 좌표에서의 워터마크 중심
        cx = w_img * self._wm_x_pct / 100.0
        cy = h_img * self._wm_y_pct / 100.0
        # 이미지 좌표에서의 좌상단
        ix = cx - wm_w / 2.0
        iy = cy - wm_h / 2.0
        # 화면 좌표로 변환
        from PyQt6.QtCore import QRect
        sx = int(ix * scale + off_x)
        sy = int(iy * scale + off_y)
        sw = int(wm_w * scale)
        sh = int(wm_h * scale)
        return QRect(sx, sy, sw, sh)

    def screen_to_image(self, pos):
        """화면 좌표를 이미지 좌표로 변환"""
        scale, off_x, off_y = self.get_scale_info()
        h, w = self.cv_image.shape[:2]
        if scale == 0:
            return 0.0, 0.0
        
        img_x = (pos.x() - off_x) / scale
        img_y = (pos.y() - off_y) / scale
        
        return max(0.0, min(img_x, float(w - 1))), max(0.0, min(img_y, float(h - 1)))

    def mousePressEvent(self, event):
        """마우스 누름 이벤트"""
        modifiers = QApplication.keyboardModifiers()
        self.setFocus()
        if self.cv_image is None:
            return

        # 워터마크 드래그 모드 — 페인팅/마스킹 차단
        if self._wm_mode and event.button() == Qt.MouseButton.LeftButton:
            modifiers_wm = QApplication.keyboardModifiers()
            if modifiers_wm == Qt.KeyboardModifier.AltModifier:
                pass  # Alt+클릭은 패닝으로 넘김
            else:
                if self._wm_overlay is not None:
                    rect = self._wm_screen_rect()
                    if rect:
                        # 모서리 근처 클릭 → 크기 조절
                        corner_margin = 18
                        corners = [rect.topLeft(), rect.topRight(),
                                   rect.bottomLeft(), rect.bottomRight()]
                        for c in corners:
                            if (event.pos() - c).manhattanLength() < corner_margin:
                                self._wm_resizing = True
                                cx, cy = rect.center().x(), rect.center().y()
                                self._wm_resize_start_dist = max(1.0, (
                                    (event.pos().x() - cx) ** 2 +
                                    (event.pos().y() - cy) ** 2
                                ) ** 0.5)
                                self._wm_resize_center = QPoint(cx, cy)
                                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                                return

                        if rect.contains(event.pos()):
                            # 오버레이 위 클릭 → 드래그 시작
                            self._wm_dragging = True
                            # 화면 좌표 기준 오프셋 기록
                            self._wm_drag_start_pos = event.pos()
                            self._wm_drag_start_x_pct = self._wm_x_pct
                            self._wm_drag_start_y_pct = self._wm_y_pct
                            self.setCursor(Qt.CursorShape.ClosedHandCursor)
                            return
                # 오버레이 밖 또는 오버레이 없음 → 클릭 위치로 이동
                scale, off_x, off_y = self.get_scale_info()
                h_img, w_img = self.cv_image.shape[:2]
                if scale > 0:
                    img_x = (event.pos().x() - off_x) / scale
                    img_y = (event.pos().y() - off_y) / scale
                    if 0 <= img_x <= w_img and 0 <= img_y <= h_img:
                        new_x_pct = img_x / w_img * 100.0
                        new_y_pct = img_y / h_img * 100.0
                        self._wm_x_pct = new_x_pct
                        self._wm_y_pct = new_y_pct
                        if self._wm_clamp:
                            self._apply_wm_clamp()
                        self.wm_position_changed.emit(self._wm_x_pct, self._wm_y_pct)
                        self.update()
                # 워터마크 모드에서는 항상 페인팅 차단
                return

        if self.is_panning and event.button() == Qt.MouseButton.LeftButton:
            self.drag_last_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
            
        if modifiers == Qt.KeyboardModifier.AltModifier:
            self.is_panning = True
            self.drag_last_pos = event.pos()  # ← pan_start_pos 대신 drag_last_pos 사용
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # ── 이동 모드 ──
        if self.move_mode and self._move_region is not None and event.button() == Qt.MouseButton.LeftButton:
            # 부유 영역 위 클릭 여부 판정
            scale, off_x, off_y = self.get_scale_info()
            ox, oy, rw, rh = self._move_origin_bbox
            nx = ox + self._move_offset_x
            ny = oy + self._move_offset_y
            # 이미지 좌표 → 스크린 좌표
            scr_x1 = int(nx * scale + off_x)
            scr_y1 = int(ny * scale + off_y)
            scr_x2 = int((nx + rw) * scale + off_x)
            scr_y2 = int((ny + rh) * scale + off_y)
            mx, my = event.pos().x(), event.pos().y()
            if scr_x1 <= mx <= scr_x2 and scr_y1 <= my <= scr_y2:
                self._move_drag_start = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # ── 그리기 모드 ──
        if self.draw_mode and event.button() == Qt.MouseButton.LeftButton:
            bx, by = self.map_to_base_coordinates(event.pos())
            bx_i, by_i = int(round(bx)), int(round(by))

            if self.draw_tool == 'eyedropper':
                self._eyedropper_at(event.pos())
            elif self.draw_tool == 'fill':
                self._flood_fill_at(event.pos())
            elif self.draw_tool == 'clone_stamp':
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    # Alt+클릭: 소스 지점 설정
                    self._clone_source = (bx_i, by_i)
                    self._clone_offset = None
                elif self._clone_source is not None:
                    # 일반 클릭: 복제 시작
                    self.push_undo_stack()
                    if self._clone_offset is None:
                        sx, sy = self._clone_source
                        self._clone_offset = (sx - bx_i, sy - by_i)
                    self._clone_active = True
                    self.last_draw_pos = event.pos()
                    self._apply_clone_at(bx_i, by_i)
                    self.rotate_image(0)
            elif self.draw_tool == 'pen':
                self.push_undo_stack()
                self._draw_pen_active = True
                self.last_draw_pos = event.pos()
            elif self.draw_tool in ('line', 'rect', 'ellipse'):
                self._draw_start = (bx_i, by_i)
                self._draw_preview_end = (bx_i, by_i)
            self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.push_undo_stack()
            self.is_drawing = True
            self.last_mouse_pos = event.pos()
            self.last_draw_pos = event.pos()

            is_bar_mode = (
                self.current_tool == 'box' and
                self.parent_editor.effect_group.checkedId() == 1
            )

            if is_bar_mode:
                self._apply_paint_tool(event.pos(), is_bar_censor=True)
                self._straight_line_anchor = event.pos()
            elif self.current_tool == 'box':
                self.start_pos = event.pos()
                self.end_pos = event.pos()
            elif self.current_tool == 'lasso':
                self.lasso_path = [event.pos()]
                self._straight_line_anchor = event.pos()
            elif self.current_tool == 'eraser':
                self._apply_paint_tool(event.pos(), prev_pos=None, is_eraser=True)
                self._straight_line_anchor = event.pos()
            elif self.current_tool == 'brush':
                self._apply_paint_tool(event.pos(), prev_pos=None, is_eraser=False)
                self._straight_line_anchor = event.pos()
        self.update()

    def mouseMoveEvent(self, event):
        """마우스 이동 이벤트"""
        self.cursor_pos = event.pos()

        # 워터마크 크기 조절
        if self._wm_resizing and self._wm_overlay is not None:
            cx = self._wm_resize_center.x()
            cy = self._wm_resize_center.y()
            cur_dist = max(1.0, ((event.pos().x() - cx) ** 2 + (event.pos().y() - cy) ** 2) ** 0.5)
            if self._wm_resize_start_dist > 0:
                ratio = cur_dist / self._wm_resize_start_dist
                self.wm_scale_changed.emit(ratio)
            return

        # 워터마크 드래그 (화면 좌표 델타 → 퍼센트 변환)
        if self._wm_dragging and self._wm_overlay is not None:
            scale, off_x, off_y = self.get_scale_info()
            h_img, w_img = self.cv_image.shape[:2]
            if scale > 0:
                dx_screen = event.pos().x() - self._wm_drag_start_pos.x()
                dy_screen = event.pos().y() - self._wm_drag_start_pos.y()
                dx_pct = (dx_screen / scale) / w_img * 100.0
                dy_pct = (dy_screen / scale) / h_img * 100.0
                self._wm_x_pct = max(0.0, min(100.0, self._wm_drag_start_x_pct + dx_pct))
                self._wm_y_pct = max(0.0, min(100.0, self._wm_drag_start_y_pct + dy_pct))
                if self._wm_clamp:
                    self._apply_wm_clamp()
                self.wm_position_changed.emit(self._wm_x_pct, self._wm_y_pct)
            self.update()
            return

        # 워터마크 모드: 오버레이 위 호버 시 커서 변경
        if self._wm_mode and self._wm_overlay is not None and not self.is_panning:
            rect = self._wm_screen_rect()
            if rect:
                corner_margin = 18
                corners = [rect.topLeft(), rect.topRight(),
                           rect.bottomLeft(), rect.bottomRight()]
                on_corner = any(
                    (event.pos() - c).manhattanLength() < corner_margin
                    for c in corners
                )
                if on_corner:
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif rect.contains(event.pos()):
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

        if self.is_panning and self.drag_last_pos:
            delta = event.pos() - self.drag_last_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self.drag_last_pos = event.pos()
            self.update()
            return

        # ── 이동 모드 드래그 ──
        if self.move_mode and self._move_drag_start is not None and self._move_region is not None:
            scale, off_x, off_y = self.get_scale_info()
            if scale > 0:
                dx = int((event.pos().x() - self._move_drag_start.x()) / scale)
                dy = int((event.pos().y() - self._move_drag_start.y()) / scale)
                self._move_offset_x += dx
                self._move_offset_y += dy
                self._move_drag_start = event.pos()
            self.update()
            return

        # ── 그리기 모드 이동 ──
        if self.draw_mode:
            if self._clone_active and self.last_draw_pos:
                # 클론 스탬프: 연속 복제
                cur_bx, cur_by = self.map_to_base_coordinates(event.pos())
                self._apply_clone_at(int(round(cur_bx)), int(round(cur_by)))
                self.rotate_image(0)
                self.last_draw_pos = event.pos()
            elif self._draw_pen_active and self.last_draw_pos:
                # 펜: 이전점→현재점 연결
                prev_bx, prev_by = self.map_to_base_coordinates(self.last_draw_pos)
                cur_bx, cur_by = self.map_to_base_coordinates(event.pos())
                pt1 = (int(round(prev_bx)), int(round(prev_by)))
                pt2 = (int(round(cur_bx)), int(round(cur_by)))
                self._draw_on_image(
                    self.display_base_image, pt1, pt2, 'pen',
                    self.draw_color, self.draw_size, self.draw_opacity, False
                )
                self.rotate_image(0)
                self.last_draw_pos = event.pos()
            elif self._draw_start is not None:
                # 직선/사각형/원: 미리보기 갱신
                bx, by = self.map_to_base_coordinates(event.pos())
                self._draw_preview_end = (int(round(bx)), int(round(by)))
            self.update()
            return

        if self.is_drawing:
            is_bar_mode = (
                self.current_tool == 'box' and 
                self.parent_editor.effect_group.checkedId() == 1
            )
            
            if is_bar_mode:
                if self._is_caps_lock_on():
                    pass  # 직선 모드: release에서 처리
                else:
                    dist_threshold = max(5, self.parent_editor.slider_strength.value())
                    dist = np.sqrt(
                        (event.pos().x() - self.last_draw_pos.x())**2 +
                        (event.pos().y() - self.last_draw_pos.y())**2
                    )
                    if dist >= dist_threshold:
                        self._apply_paint_tool(event.pos(), is_bar_censor=True)
                        self.last_draw_pos = event.pos()
            
            elif self.current_tool == 'box':
                self.end_pos = event.pos()
            elif self.current_tool == 'lasso':
                caps_on = self._is_caps_lock_on()
                if caps_on:
                    # Caps Lock ON: 직선 모드 - 앵커에서 현재 위치까지 직선 미리보기만
                    # (실제 포인트 추가는 mouseReleaseEvent나 다음 클릭에서)
                    pass
                else:
                    # 자석 올가미 모드면 에지에 스냅, 아니면 일반
                    if self.magnetic_lasso:
                        snap_pos = self._snap_lasso_point(event.pos())
                        self.lasso_path.append(snap_pos)
                    else:
                        self.lasso_path.append(event.pos())
            elif self.current_tool == 'eraser':
                if self._is_caps_lock_on():
                    pass  # 직선 모드: release에서 처리
                else:
                    self._apply_paint_tool(
                        event.pos(), prev_pos=self.last_mouse_pos, is_eraser=True
                    )
            elif self.current_tool == 'brush':
                if self._is_caps_lock_on():
                    pass  # 직선 모드: release에서 처리
                else:
                    self._apply_paint_tool(
                        event.pos(), prev_pos=self.last_mouse_pos, is_eraser=False
                    )
            
            self.last_mouse_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        """마우스 릴리즈 이벤트"""
        if self._wm_resizing:
            self._wm_resizing = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.wm_resize_finished.emit()
            return

        if self._wm_dragging:
            self._wm_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self.is_panning:
            self.drag_last_pos = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        # ── 이동 모드 릴리즈 ──
        if self.move_mode and self._move_drag_start is not None:
            self._move_drag_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # ── 그리기 모드 릴리즈 ──
        if self.draw_mode and event.button() == Qt.MouseButton.LeftButton:
            if self._clone_active:
                self._clone_active = False
                self.last_draw_pos = None
            elif self._draw_pen_active:
                self._draw_pen_active = False
                self.last_draw_pos = None
            elif self._draw_start is not None and self._draw_preview_end is not None:
                self.push_undo_stack()
                self._draw_on_image(
                    self.display_base_image,
                    self._draw_start, self._draw_preview_end,
                    self.draw_tool, self.draw_color,
                    self.draw_size, self.draw_opacity, self.draw_filled
                )
                self.rotate_image(0)
                self._draw_start = None
                self._draw_preview_end = None
            self.update()
            return

        if self.is_drawing and event.button() == Qt.MouseButton.LeftButton:
            self.is_drawing = False
            caps_on = self._is_caps_lock_on()

            # Caps Lock 직선 모드: 사각형+검은띠는 앵커→현재 위치 직선으로 간격마다 스탬프
            is_bar_mode = (
                self.current_tool == 'box' and
                self.parent_editor.effect_group.checkedId() == 1
            )
            if caps_on and is_bar_mode:
                if self._straight_line_anchor:
                    self._stamp_bars_along_line(
                        self._straight_line_anchor, event.pos()
                    )
                self._straight_line_anchor = event.pos()
                self.last_mouse_pos = None
                self.update()
                return

            # Caps Lock 직선 모드: 브러시/지우개는 앵커→현재 위치 직선
            if caps_on and self.current_tool in ['brush', 'eraser']:
                if self._straight_line_anchor and self.last_mouse_pos:
                    is_eraser = self.current_tool == 'eraser'
                    self._apply_paint_tool(
                        event.pos(),
                        prev_pos=self._straight_line_anchor,
                        is_eraser=is_eraser
                    )
                self._straight_line_anchor = event.pos()

            # Caps Lock 직선 모드: 올가미는 앵커→현재 위치 직선 세그먼트 추가
            if caps_on and self.current_tool == 'lasso':
                self.lasso_path.append(event.pos())
                self._straight_line_anchor = event.pos()
                # 올가미는 아직 닫지 않음 (더블클릭이나 다음 동작에서 닫힘)
                self.last_mouse_pos = None
                self.update()
                return

            self.last_mouse_pos = None

            is_bar_mode = (
                self.current_tool == 'box' and
                self.parent_editor.effect_group.checkedId() == 1
            )

            if not is_bar_mode and self.current_tool in ['box', 'lasso']:
                screen_pts = []
                if self.current_tool == 'box':
                    x1, y1 = self.start_pos.x(), self.start_pos.y()
                    x2, y2 = self.end_pos.x(), self.end_pos.y()
                    screen_pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                else:
                    raw_pts = [(p.x(), p.y()) for p in self.lasso_path]
                    # 떨림 보정 (Caps Lock 직선 모드가 아닐 때만)
                    if not caps_on:
                        screen_pts = self._smooth_lasso_path(raw_pts)
                    else:
                        screen_pts = raw_pts

                if len(screen_pts) > 2:
                    base_pts = []
                    for sp in screen_pts:
                        bx, by = self.map_to_base_coordinates(
                            QPoint(int(sp[0]), int(sp[1]))
                        )
                        base_pts.append([bx, by])
                    pts = np.round(np.array(base_pts)).astype(np.int32)
                    if self.selection_mask is not None:
                        cv2.fillPoly(self.selection_mask, [pts], 255)
            
            self.start_pos = None
            self.end_pos = None
            self.lasso_path = []
        self.update()
  
    def paintEvent(self, event):
        """페인트 이벤트"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        
        if self.cv_image is None: 
            return
        
        scale, off_x, off_y = self.get_scale_info()
        h, w, ch = self.cv_image.shape
        
        rgb_image = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2RGB)
        q_img = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
        disp_w = int(w * scale)
        disp_h = int(h * scale)
        
        from PyQt6.QtCore import QRect
        img_rect = QRect(off_x, off_y, disp_w, disp_h)
        painter.drawImage(img_rect, q_img)

        # 워터마크 미리보기 오버레이
        if self._wm_overlay is not None:
            wm_rect = self._wm_screen_rect()
            if wm_rect:
                oh, ow = self._wm_overlay.shape[:2]
                if self._wm_overlay.shape[2] == 4:
                    qfmt = QImage.Format.Format_RGBA8888
                    rgb_overlay = cv2.cvtColor(self._wm_overlay, cv2.COLOR_BGRA2RGBA)
                    bpl = ow * 4
                else:
                    qfmt = QImage.Format.Format_RGB888
                    rgb_overlay = cv2.cvtColor(self._wm_overlay, cv2.COLOR_BGR2RGB)
                    bpl = ow * 3
                q_wm = QImage(rgb_overlay.data, ow, oh, bpl, qfmt)
                painter.drawImage(wm_rect, q_wm)
                # 드래그 가능 표시: 점선 테두리
                painter.setPen(QPen(Qt.GlobalColor.cyan, 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(wm_rect)
                # 리사이즈 핸들 (모서리)
                handle_size = 8
                from PyQt6.QtGui import QBrush
                painter.setPen(QPen(Qt.GlobalColor.white, 1))
                painter.setBrush(QBrush(Qt.GlobalColor.cyan))
                for corner in [wm_rect.topLeft(), wm_rect.topRight(),
                               wm_rect.bottomLeft(), wm_rect.bottomRight()]:
                    painter.drawRect(
                        corner.x() - handle_size // 2,
                        corner.y() - handle_size // 2,
                        handle_size, handle_size
                    )

        # 이동 모드: 부유 영역 미리보기
        if self.move_mode and self._move_region is not None and self._move_origin_bbox is not None:
            ox, oy, rw, rh = self._move_origin_bbox

            # 회전/크기 적용된 영역 생성
            region_rgba = np.zeros((rh, rw, 4), dtype=np.uint8)
            region_rgb = cv2.cvtColor(self._move_region, cv2.COLOR_BGR2RGB)
            region_rgba[:, :, :3] = region_rgb
            region_rgba[:, :, 3] = self._move_mask

            # 크기 변환
            ms = self._move_scale
            if ms != 1.0:
                new_w = max(1, int(rw * ms))
                new_h = max(1, int(rh * ms))
                region_rgba = cv2.resize(region_rgba, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
            else:
                new_w, new_h = rw, rh

            # 회전 변환
            mr = self._move_rotation
            if mr != 0:
                center = (new_w // 2, new_h // 2)
                M = cv2.getRotationMatrix2D(center, mr, 1.0)
                cos_v = np.abs(M[0, 0])
                sin_v = np.abs(M[0, 1])
                rot_w = int(new_h * sin_v + new_w * cos_v)
                rot_h = int(new_h * cos_v + new_w * sin_v)
                M[0, 2] += (rot_w / 2) - center[0]
                M[1, 2] += (rot_h / 2) - center[1]
                region_rgba = cv2.warpAffine(region_rgba, M, (rot_w, rot_h),
                                             borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
                new_w, new_h = rot_w, rot_h

            nx = ox + self._move_offset_x
            ny = oy + self._move_offset_y
            scr_x = int(nx * scale + off_x)
            scr_y = int(ny * scale + off_y)
            scr_w = int(new_w * scale)
            scr_h = int(new_h * scale)

            q_region = QImage(region_rgba.data, new_w, new_h, new_w * 4, QImage.Format.Format_RGBA8888)
            from PyQt6.QtCore import QRect as QR
            painter.drawImage(QR(scr_x, scr_y, scr_w, scr_h), q_region)

            # 파란 점선 테두리
            painter.setPen(QPen(Qt.GlobalColor.cyan, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(scr_x, scr_y, scr_w, scr_h)

        # 마스크 오버레이
        if self.selection_mask is not None and self.display_base_image is not None:
            h_b, w_b = self.display_base_image.shape[:2]
            center = (w_b // 2, h_b // 2)
            M = cv2.getRotationMatrix2D(center, self.rotation_angle, 1.0)
            
            cos = np.abs(M[0, 0])
            sin = np.abs(M[0, 1])
            new_w = int((h_b * sin) + (w_b * cos))
            new_h = int((h_b * cos) + (w_b * sin))
            M[0, 2] += (new_w / 2) - center[0]
            M[1, 2] += (new_h / 2) - center[1]
            
            rotated_mask = cv2.warpAffine(
                self.selection_mask, M, (new_w, new_h), 
                flags=cv2.INTER_NEAREST
            )
            mask_display = np.zeros((new_h, new_w, 4), dtype=np.uint8)
            mask_display[rotated_mask > 0] = [255, 0, 0, 100] 
            
            q_mask = QImage(
                mask_display.data, new_w, new_h, 
                new_w * 4, QImage.Format.Format_RGBA8888
            )
            painter.drawImage(img_rect, q_mask)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_bar_mode = (
            self.current_tool == 'box' and 
            self.parent_editor.effect_group.checkedId() == 1
        )
        
        # 그리기 중 미리보기
        if self.is_drawing:
            if not is_bar_mode:
                pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                if self.current_tool == 'box' and self.start_pos and self.end_pos:
                    from PyQt6.QtCore import QRect
                    painter.drawRect(QRect(self.start_pos, self.end_pos).normalized())
                elif self.current_tool == 'lasso' and len(self.lasso_path) > 1:
                    painter.drawPolyline(QPolygon(self.lasso_path))

            # Caps Lock 직선 모드 미리보기: 앵커 → 현재 커서 위치까지 점선
            caps_on = self._is_caps_lock_on()
            if caps_on and self._straight_line_anchor and self.cursor_pos:
                dash_pen = QPen(Qt.GlobalColor.cyan, 2, Qt.PenStyle.DashLine)
                painter.setPen(dash_pen)
                painter.drawLine(self._straight_line_anchor, self.cursor_pos)
        
        # 커서 미리보기
        if (self.current_tool in ['eraser', 'brush'] or is_bar_mode) and self.cursor_pos:
            if is_bar_mode:
                bw = int(self.parent_editor.slider_bar_w.value() * scale)
                bh = int(self.parent_editor.slider_bar_h.value() * scale)
                
                cx, cy = self.cursor_pos.x(), self.cursor_pos.y()
                
                painter.setPen(QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine))
                from PyQt6.QtCore import QRect
                painter.drawRect(QRect(cx - bw//2, cy - bh//2, bw, bh))
                    
            else:
                screen_radius = int(self.brush_size * scale)
                color = (
                    Qt.GlobalColor.white if self.current_tool == 'eraser' 
                    else Qt.GlobalColor.green
                )
                painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(self.cursor_pos, screen_radius, screen_radius)

        # ── 그리기 모드 미리보기 ──
        if self.draw_mode and self._draw_start is not None and self._draw_preview_end is not None:
            # 이미지 좌표 → 스크린 좌표 변환
            s1x = int(self._draw_start[0] * scale + off_x)
            s1y = int(self._draw_start[1] * scale + off_y)
            s2x = int(self._draw_preview_end[0] * scale + off_x)
            s2y = int(self._draw_preview_end[1] * scale + off_y)

            preview_pen = QPen(Qt.GlobalColor.cyan, 2, Qt.PenStyle.DashLine)
            painter.setPen(preview_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if self.draw_tool == 'line':
                painter.drawLine(s1x, s1y, s2x, s2y)
            elif self.draw_tool == 'rect':
                from PyQt6.QtCore import QRect as QR
                painter.drawRect(QR(
                    min(s1x, s2x), min(s1y, s2y),
                    abs(s2x - s1x), abs(s2y - s1y)
                ))
            elif self.draw_tool == 'ellipse':
                from PyQt6.QtCore import QRect as QR
                painter.drawEllipse(QR(
                    min(s1x, s2x), min(s1y, s2y),
                    abs(s2x - s1x), abs(s2y - s1y)
                ))

        # 그리기 모드 커서 미리보기 (펜 크기)
        if self.draw_mode and self.draw_tool == 'pen' and self.cursor_pos:
            screen_r = int(self.draw_size * scale / 2)
            painter.setPen(QPen(Qt.GlobalColor.cyan, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.cursor_pos, max(1, screen_r), max(1, screen_r))

        # 클론 스탬프 커서 + 소스 표시
        if self.draw_mode and self.draw_tool == 'clone_stamp':
            screen_r = max(1, int(self.draw_size * scale / 2))
            # 대상 위치 (커서)
            if self.cursor_pos:
                painter.setPen(QPen(Qt.GlobalColor.cyan, 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(self.cursor_pos, screen_r, screen_r)
            # 소스 위치 십자
            if self._clone_source is not None:
                sx = int(self._clone_source[0] * scale + off_x)
                sy = int(self._clone_source[1] * scale + off_y)
                cross = 10
                painter.setPen(QPen(QColor(255, 100, 100), 2))
                painter.drawLine(sx - cross, sy, sx + cross, sy)
                painter.drawLine(sx, sy - cross, sx, sy + cross)
                # 클론 중이면 소스 브러시 원도 표시
                if self._clone_active and self.cursor_pos and self._clone_offset:
                    cbx, cby = self.map_to_base_coordinates(self.cursor_pos)
                    live_sx = int((cbx + self._clone_offset[0]) * scale + off_x)
                    live_sy = int((cby + self._clone_offset[1]) * scale + off_y)
                    painter.setPen(QPen(QColor(255, 100, 100), 1, Qt.PenStyle.DashLine))
                    painter.drawEllipse(QPoint(live_sx, live_sy), screen_r, screen_r)

    # ──────────────────────────────────────────────────
    #  크롭 / 리사이즈 / 이미지 조정
    # ──────────────────────────────────────────────────

    def crop_to_selection(self, x: int, y: int, w: int, h: int):
        """선택 영역으로 이미지 크롭"""
        if self.display_base_image is None:
            return
        self.display_base_image = self.display_base_image[y:y+h, x:x+w].copy()
        self.pristine_image = self.pristine_image[y:y+h, x:x+w].copy()
        img_h, img_w = self.display_base_image.shape[:2]
        self.selection_mask = np.zeros((img_h, img_w), dtype=np.uint8)
        self._edge_map_dirty = True
        self.rotation_angle = 0
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.cv_image = self.display_base_image.copy()
        self.update()

    def resize_image(self, w: int, h: int):
        """이미지 리사이즈"""
        if self.display_base_image is None:
            return
        self.display_base_image = cv2.resize(self.display_base_image, (w, h), interpolation=cv2.INTER_LANCZOS4)
        self.pristine_image = cv2.resize(self.pristine_image, (w, h), interpolation=cv2.INTER_LANCZOS4)
        self.selection_mask = np.zeros((h, w), dtype=np.uint8)
        self._edge_map_dirty = True
        self.rotation_angle = 0
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.cv_image = self.display_base_image.copy()
        self.update()

    def rotate_90_cw(self):
        """90도 시계방향 회전"""
        if self.display_base_image is None:
            return
        self.display_base_image = cv2.rotate(self.display_base_image, cv2.ROTATE_90_CLOCKWISE)
        self.pristine_image = cv2.rotate(self.pristine_image, cv2.ROTATE_90_CLOCKWISE)
        img_h, img_w = self.display_base_image.shape[:2]
        self.selection_mask = np.zeros((img_h, img_w), dtype=np.uint8)
        self._edge_map_dirty = True
        self.rotation_angle = 0
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.cv_image = self.display_base_image.copy()
        self.update()

    def rotate_90_ccw(self):
        """90도 반시계방향 회전"""
        if self.display_base_image is None:
            return
        self.display_base_image = cv2.rotate(self.display_base_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        self.pristine_image = cv2.rotate(self.pristine_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        img_h, img_w = self.display_base_image.shape[:2]
        self.selection_mask = np.zeros((img_h, img_w), dtype=np.uint8)
        self._edge_map_dirty = True
        self.rotation_angle = 0
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.cv_image = self.display_base_image.copy()
        self.update()

    def flip_horizontal(self):
        """좌우 반전"""
        if self.display_base_image is None:
            return
        self.display_base_image = cv2.flip(self.display_base_image, 1)
        self.pristine_image = cv2.flip(self.pristine_image, 1)
        img_h, img_w = self.display_base_image.shape[:2]
        self.selection_mask = np.zeros((img_h, img_w), dtype=np.uint8)
        self._edge_map_dirty = True
        self.cv_image = self.display_base_image.copy()
        self.update()

    def flip_vertical(self):
        """상하 반전"""
        if self.display_base_image is None:
            return
        self.display_base_image = cv2.flip(self.display_base_image, 0)
        self.pristine_image = cv2.flip(self.pristine_image, 0)
        img_h, img_w = self.display_base_image.shape[:2]
        self.selection_mask = np.zeros((img_h, img_w), dtype=np.uint8)
        self._edge_map_dirty = True
        self.cv_image = self.display_base_image.copy()
        self.update()

    @staticmethod
    def _apply_adjustments(img, brightness: int, contrast: int, saturation: int):
        """밝기/대비/채도 조정 적용 (내부 함수)"""
        result = img.copy()

        # 대비
        if contrast != 0:
            alpha = 1.0 + contrast / 100.0
            result = cv2.convertScaleAbs(result, alpha=alpha, beta=0)

        # 밝기
        if brightness != 0:
            result = cv2.convertScaleAbs(result, alpha=1.0, beta=brightness)

        # 채도
        if saturation != 0:
            hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] *= (1.0 + saturation / 100.0)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
            result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        return result

    def set_adjustment_preview(self, brightness: int, contrast: int, saturation: int):
        """이미지 조정 실시간 프리뷰"""
        if self.display_base_image is None:
            return
        if brightness == 0 and contrast == 0 and saturation == 0:
            self.cv_image = self.display_base_image.copy()
            if self.rotation_angle != 0:
                self.rotate_image(0)
            else:
                self.update()
            return
        adjusted = self._apply_adjustments(self.display_base_image, brightness, contrast, saturation)
        self.cv_image = adjusted
        if self.rotation_angle != 0:
            # 회전 적용된 상태면 회전도 다시 적용
            h, w = adjusted.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, self.rotation_angle, 1.0)
            cos_v = np.abs(M[0, 0])
            sin_v = np.abs(M[0, 1])
            new_w = int((h * sin_v) + (w * cos_v))
            new_h = int((h * cos_v) + (w * sin_v))
            M[0, 2] += (new_w / 2) - center[0]
            M[1, 2] += (new_h / 2) - center[1]
            self.cv_image = cv2.warpAffine(adjusted, M, (new_w, new_h))
        self.update()

    def apply_adjustment(self, brightness: int, contrast: int, saturation: int):
        """이미지 조정 실제 적용 (display_base_image에 반영)"""
        if self.display_base_image is None:
            return
        self.push_undo_stack()
        self.display_base_image = self._apply_adjustments(
            self.display_base_image, brightness, contrast, saturation
        )
        self._edge_map_dirty = True
        self.rotate_image(0)

    def clear_adjustment_preview(self):
        """이미지 조정 프리뷰 제거, display_base_image로 복원"""
        if self.display_base_image is None:
            return
        self.rotate_image(0)