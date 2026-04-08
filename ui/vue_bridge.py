# ui/vue_bridge.py
"""
PyQt6 ↔ Vue 통신 브릿지 (QWebChannel)
위젯 프록시 값 동기화 + 액션 디스패치 + 이미지 생성 이벤트
"""
import json
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class VueBridge(QObject):
    """Vue 프론트엔드와 통신하는 중앙 브릿지"""

    # ── Python → Vue 시그널 ──
    imageGenerated = pyqtSignal(str)
    generationStarted = pyqtSignal()
    generationError = pyqtSignal(str)

    editorImageLoaded = pyqtSignal(str)   # file path
    i2iImageLoaded = pyqtSignal(str)     # file path
    galleryFolderLoaded = pyqtSignal(str)  # folder path
    inpaintImageLoaded = pyqtSignal(str)   # file path (PngInfo + InpaintView 공용)
    searchStatus = pyqtSignal(str)         # status message

    loraInserted = pyqtSignal(str)   # JSON {name, weight}
    yoloModelUpdated = pyqtSignal(str)  # model label text

    # 위젯 값/속성 동기화 (Python → Vue)
    widgetValueChanged = pyqtSignal(str, str)       # (widget_id, value)
    widgetPropertyChanged = pyqtSignal(str, str, str)  # (widget_id, prop, value_json)

    # 배치 업데이트 (설정 로드 시 한번에 전송)
    batchUpdate = pyqtSignal(str)  # JSON: {widget_id: value, ...}

    # 탭 전환
    tabChanged = pyqtSignal(str)  # tab_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxies = {}  # widget_id → proxy 객체
        self._batch_mode = False
        self._batch_buffer = {}
        self._action_handler = None  # 액션 디스패처 (메인 윈도우에서 설정)

    def _register_proxy(self, widget_id: str, proxy):
        """위젯 프록시 등록 + 부모 설정 (GC 방지)"""
        self._proxies[widget_id] = proxy
        if hasattr(proxy, 'setParent') and proxy.parent() is None:
            proxy.setParent(self)

    def set_action_handler(self, handler):
        """액션 핸들러 설정 (메인 윈도우의 메서드를 디스패치)"""
        self._action_handler = handler

    # ── Python → Vue 데이터 전송 ──

    def pushWidgetValue(self, widget_id: str, value: str):
        """위젯 값을 Vue로 전송"""
        if self._batch_mode:
            self._batch_buffer[widget_id] = value
        else:
            self.widgetValueChanged.emit(widget_id, str(value))

    def pushWidgetProperty(self, widget_id: str, prop: str, value):
        """위젯 속성을 Vue로 전송"""
        self.widgetPropertyChanged.emit(widget_id, prop, json.dumps(value))

    def beginBatchUpdate(self):
        """배치 모드 시작 (load_settings 등에서 사용)"""
        self._batch_mode = True
        self._batch_buffer = {}

    def endBatchUpdate(self):
        """배치 모드 종료 — 버퍼의 모든 값을 한번에 전송"""
        self._batch_mode = False
        if self._batch_buffer:
            self.batchUpdate.emit(json.dumps(self._batch_buffer))
            self._batch_buffer = {}

    # ── 이미지 생성 이벤트 ──

    def send_image(self, path: str, width: int, height: int, seed: int):
        data = json.dumps({
            'path': path.replace('\\', '/'),
            'width': width, 'height': height, 'seed': seed,
        })
        self.imageGenerated.emit(data)

    def send_start(self):
        self.generationStarted.emit()

    def send_error(self, msg: str):
        self.generationError.emit(msg)

    # ── Vue → Python 슬롯 ──

    @pyqtSlot(str, str)
    @pyqtSlot(str, float)
    @pyqtSlot(str, bool)
    def onWidgetChanged(self, widget_id: str, value):
        """Vue에서 사용자가 위젯 값을 변경했을 때 (타입 무관 수용)"""
        proxy = self._proxies.get(widget_id)
        if proxy:
            # 문자열로 변환하여 전달
            proxy._on_vue_changed(str(value))

    @pyqtSlot(str, str)
    def onAction(self, action: str, payload_json: str):
        """Vue에서 버튼 클릭 등 액션 요청"""
        if self._action_handler:
            try:
                # payload가 이미 dict인 경우와 JSON 문자열인 경우 모두 대응
                if isinstance(payload_json, str):
                    payload = json.loads(payload_json) if payload_json else {}
                else:
                    payload = payload_json
                self._action_handler(action, payload)
            except Exception as e:
                print(f"[VueBridge] Action error: {action} - {e}")

    @pyqtSlot(str, str)
    def requestAction(self, action: str, payload_json: str):
        """onAction의 별칭 - Vue에서 더 직관적으로 호출 가능하도록"""
        self.onAction(action, payload_json)

    @pyqtSlot(str)
    def onTabSwitch(self, tab_id: str):
        """Vue에서 탭 전환 요청"""
        self.tabChanged.emit(tab_id)

    @pyqtSlot(str, result=str)
    def getWidgetValue(self, widget_id: str) -> str:
        """Vue에서 위젯 값 동기 요청"""
        proxy = self._proxies.get(widget_id)
        if not proxy:
            return ""
        if hasattr(proxy, 'text'):
            return proxy.text()
        if hasattr(proxy, 'toPlainText'):
            return proxy.toPlainText()
        if hasattr(proxy, 'isChecked'):
            return "true" if proxy.isChecked() else "false"
        if hasattr(proxy, 'currentText'):
            return proxy.currentText()
        return ""

    @pyqtSlot(result=str)
    def getAllWidgetValues(self) -> str:
        """모든 위젯 값을 JSON으로 반환 (초기 로드용)"""
        result = {}
        for wid, proxy in self._proxies.items():
            if hasattr(proxy, 'text'):
                result[wid] = proxy.text()
            elif hasattr(proxy, 'toPlainText'):
                result[wid] = proxy.toPlainText()
            elif hasattr(proxy, 'isChecked'):
                result[wid] = "true" if proxy.isChecked() else "false"
            elif hasattr(proxy, 'currentText'):
                result[wid] = proxy.currentText()
        return json.dumps(result)

    @pyqtSlot(result=str)
    def getSettings(self) -> str:
        return json.dumps({'status': 'ok'})

    # ── Editor ──

    @pyqtSlot(str, str, str, result=str)
    def editorProcess(self, image_path: str, operation: str, params_json: str) -> str:
        """에디터 이미지 처리 (Python OpenCV)"""
        try:
            import cv2
            import numpy as np
            import os
            
            # 경로 정규화 (file:/// 제거 및 슬라이시 방향 수정)
            clean_path = image_path.replace('file:///', '').replace('/', os.sep)
            if not os.path.exists(clean_path):
                print(f"[Editor] File not found: {clean_path}")
                return json.dumps({'error': f'파일을 찾을 수 없습니다: {clean_path}'})

            # params가 객체로 올 수도 있고 JSON 문자열로 올 수도 있음
            if isinstance(params_json, str):
                params = json.loads(params_json) if params_json else {}
            else:
                params = params_json

            img = cv2.imread(clean_path)
            if img is None:
                return json.dumps({'error': '이미지를 읽을 수 없습니다 (OpenCV)'})

            # ── 마스크 처리 (base64 PNG → numpy) ──
            mask = None
            mask_b64 = params.get('mask_base64')
            if mask_b64:
                import base64
                from io import BytesIO
                from PIL import Image as PILImage
                header, b64data = mask_b64.split(',', 1) if ',' in mask_b64 else ('', mask_b64)
                mask_bytes = base64.b64decode(b64data)
                mask_pil = PILImage.open(BytesIO(mask_bytes)).convert('L')
                mask = np.array(mask_pil)
                if mask.shape[:2] != img.shape[:2]:
                    mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

            # 선택 영역 추출 (좌표 정수화)
            sel = params.get('selection')
            if sel:
                x1, y1 = int(float(sel.get('x', 0))), int(float(sel.get('y', 0)))
                x2 = x1 + int(float(sel.get('w', img.shape[1])))
                y2 = y1 + int(float(sel.get('h', img.shape[0])))
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
            else:
                x1, y1, x2, y2 = 0, 0, img.shape[1], img.shape[0]

            has_roi = x2 > x1 and y2 > y1

            # ── 마스크 기반 효과 (정밀 적용) ──
            def _apply_effect_with_mask(src, effect_mask, effect_type, strength_val):
                """마스크 영역에만 효과 적용"""
                result = src.copy()
                if effect_type == 'mosaic':
                    s = max(2, strength_val)
                    h_i, w_i = src.shape[:2]
                    small = cv2.resize(src, (max(1, w_i // s), max(1, h_i // s)))
                    mosaic = cv2.resize(small, (w_i, h_i), interpolation=cv2.INTER_NEAREST)
                    alpha = (effect_mask > 127).astype(np.float32)
                    alpha3 = np.stack([alpha] * 3, axis=-1)
                    result = (mosaic * alpha3 + src * (1 - alpha3)).astype(np.uint8)
                elif effect_type == 'censor_bar':
                    result[effect_mask > 127] = 0
                elif effect_type == 'blur':
                    k = max(1, strength_val) | 1
                    blurred = cv2.GaussianBlur(src, (k, k), 0)
                    alpha = (effect_mask > 127).astype(np.float32)
                    alpha3 = np.stack([alpha] * 3, axis=-1)
                    result = (blurred * alpha3 + src * (1 - alpha3)).astype(np.uint8)
                return result

            if operation in ('mosaic', 'censor_bar', 'blur'):
                strength_val = int(params.get('strength', 15))
                if mask is not None:
                    # 마스크 기반 정밀 적용
                    img = _apply_effect_with_mask(img, mask, operation, strength_val)
                elif has_roi:
                    # 사각형 영역 기반 적용 (fallback)
                    roi = img[y1:y2, x1:x2]
                    if operation == 'mosaic':
                        h_r, w_r = roi.shape[:2]
                        small = cv2.resize(roi, (max(1, w_r // max(2, strength_val)), max(1, h_r // max(2, strength_val))))
                        roi = cv2.resize(small, (w_r, h_r), interpolation=cv2.INTER_NEAREST)
                    elif operation == 'censor_bar':
                        roi[:] = 0
                    elif operation == 'blur':
                        k = max(1, strength_val) | 1
                        roi = cv2.GaussianBlur(roi, (k, k), 0)
                    img[y1:y2, x1:x2] = roi

            elif operation in ('auto_censor', 'auto_detect'):
                # YOLO 기반 자동 검열 / 마스크만 감지
                try:
                    from tabs.editor.mosaic_panel import _load_yolo_model_paths
                    model_paths = _load_yolo_model_paths()
                    if not model_paths:
                        return json.dumps({'error': 'YOLO 모델을 먼저 추가하세요 (+ADD .PT)'})
                    conf = float(params.get('confidence', 0.25))
                    from ultralytics import YOLO
                    h_img, w_img = img.shape[:2]
                    combined_mask = np.zeros((h_img, w_img), dtype=np.uint8)
                    detect_count = 0
                    for mp in model_paths:
                        if not os.path.exists(mp): continue
                        model = YOLO(mp)
                        results = model(img, conf=conf)
                        for r in results:
                            # 세그먼트 마스크 우선 (성기 형태에 맞춤)
                            if r.masks is not None:
                                for m_tensor in r.masks.data:
                                    m_np = m_tensor.cpu().numpy().astype(np.float32)
                                    m_resized = cv2.resize(m_np, (w_img, h_img), interpolation=cv2.INTER_LINEAR)
                                    combined_mask[m_resized > 0.3] = 255
                                    detect_count += 1
                            # 마스크 없으면 박스 fallback
                            if r.masks is None and r.boxes is not None:
                                for box in r.boxes.xyxy:
                                    bx1, by1, bx2, by2 = map(int, box.tolist())
                                    bx1, by1 = max(0, bx1), max(0, by1)
                                    bx2, by2 = min(w_img, bx2), min(h_img, by2)
                                    combined_mask[by1:by2, bx1:bx2] = 255
                                    detect_count += 1
                    print(f"[YOLO] Detected {detect_count} regions, mask coverage: {combined_mask.sum() / 255}")

                    if operation == 'auto_detect':
                        # MASK ONLY: 마스크를 base64로 반환 (적용 안함)
                        import base64
                        from io import BytesIO
                        from PIL import Image as PILImage
                        mask_pil = PILImage.fromarray(combined_mask)
                        buf = BytesIO()
                        mask_pil.save(buf, format='PNG')
                        mask_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
                        return json.dumps({'mask_base64': mask_b64, 'detect_count': detect_count, 'path': clean_path})
                    else:
                        # AUTO CENSOR: 감지 + 모자이크 적용
                        if combined_mask.any():
                            # 마스크 약간 확장 (dilate)으로 경계 커버
                            kernel = np.ones((5, 5), np.uint8)
                            combined_mask = cv2.dilate(combined_mask, kernel, iterations=2)
                            img = _apply_effect_with_mask(img, combined_mask, 'mosaic', 15)
                        else:
                            return json.dumps({'error': f'감지된 영역이 없습니다 (conf={conf})'})
                except Exception as e:
                    import traceback; traceback.print_exc()
                    return json.dumps({'error': f'Auto censor 실패: {e}'})

            elif operation == 'text_watermark':
                # 텍스트 워터마크
                from PIL import Image as PILImage, ImageDraw, ImageFont
                pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert('RGBA')
                overlay = PILImage.new('RGBA', pil_img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                text = params.get('text', 'Watermark')
                font_size = int(params.get('fontSize', 36))
                opacity = float(params.get('opacity', 0.5))
                x_pct = float(params.get('xPct', 50))
                y_pct = float(params.get('yPct', 50))
                rotation = float(params.get('rotation', 0))
                try:
                    font_family = params.get('fontFamily', 'Arial')
                    font = ImageFont.truetype(font_family, font_size)
                except:
                    font = ImageFont.load_default()
                alpha_val = int(opacity * 255)
                color = (255, 255, 255, alpha_val)
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x = int(pil_img.width * x_pct / 100 - tw / 2)
                y = int(pil_img.height * y_pct / 100 - th / 2)

                if params.get('tile'):
                    # 타일 반복
                    for ty in range(-th, pil_img.height + th, th + 40):
                        for tx in range(-tw, pil_img.width + tw, tw + 40):
                            draw.text((tx, ty), text, fill=color, font=font)
                else:
                    draw.text((x, y), text, fill=color, font=font)

                if rotation != 0:
                    overlay = overlay.rotate(-rotation, expand=False, center=(pil_img.width // 2, pil_img.height // 2))
                result = PILImage.alpha_composite(pil_img, overlay)
                img = cv2.cvtColor(np.array(result.convert('RGB')), cv2.COLOR_RGB2BGR)

            elif operation == 'image_watermark':
                return json.dumps({'error': '이미지 워터마크: 먼저 이미지를 로드하세요'})

            elif operation == 'rotate_cw':
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            elif operation == 'rotate_ccw':
                img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif operation == 'flip_h':
                img = cv2.flip(img, 1)
            elif operation == 'flip_v':
                img = cv2.flip(img, 0)
            elif operation == 'resize':
                w = int(params.get('width', img.shape[1]))
                h = int(params.get('height', img.shape[0]))
                img = cv2.resize(img, (w, h))
            elif operation == 'crop' and has_roi:
                img = img[y1:y2, x1:x2]
            elif operation == 'remove_bg':
                try:
                    from rembg import remove
                    from PIL import Image as PILImage
                    pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                    result = remove(pil_img)
                    img = cv2.cvtColor(np.array(result), cv2.COLOR_RGBA2BGRA)
                except Exception as e:
                    return json.dumps({'error': f'배경 제거 실패: {e}'})
            
            elif operation == 'color_adjust':
                b_val = params.get('brightness', 0)
                c_val = params.get('contrast', 0)
                s_val = params.get('saturation', 0)
                if b_val != 0: img = cv2.convertScaleAbs(img, alpha=1, beta=b_val)
                if c_val != 0:
                    factor = (100 + c_val) / 100.0
                    img = cv2.convertScaleAbs(img, alpha=factor, beta=0)
                if s_val != 0:
                    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
                    hsv[:,:,1] *= (100 + s_val) / 100.0
                    hsv[:,:,1] = np.clip(hsv[:,:,1], 0, 255)
                    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

            # 결과 저장
            import time, random as rnd
            out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'image_cache', 'editor_temp')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"edited_{int(time.time())}_{rnd.randint(100,999)}.png")
            cv2.imwrite(out_path, img)
                
            return json.dumps({'path': out_path.replace('\\', '/'), 'width': img.shape[1], 'height': img.shape[0]})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return json.dumps({'error': str(e)})

    # ── 갤러리 ──

    @pyqtSlot(str, result=str)
    def getGalleryImages(self, folder: str) -> str:
        """폴더의 이미지 목록 반환"""
        import os
        from config import OUTPUT_DIR
        target = folder if folder else OUTPUT_DIR
        if not os.path.isdir(target):
            return json.dumps([])
        exts = ('.png', '.jpg', '.jpeg', '.webp')
        files = []
        try:
            for f in sorted(os.listdir(target), key=lambda x: os.path.getmtime(os.path.join(target, x)), reverse=True):
                if f.lower().endswith(exts):
                    fp = os.path.join(target, f).replace('\\', '/')
                    files.append(fp)
        except Exception: pass
        return json.dumps(files)

    @pyqtSlot(result=str)
    def getFavorites(self) -> str:
        """즐겨찾기 목록 반환"""
        import os
        from config import FAVORITES_FILE
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return json.dumps([])

    searchResultsReady = pyqtSignal(str)   # JSON results
    queueUpdated = pyqtSignal(str)         # JSON queue state
    eventSearchResults = pyqtSignal(str)   # JSON event results
    generationProgress = pyqtSignal(int, int)  # current, total steps

    @pyqtSlot(str)
    def searchDanbooru(self, query_json: str):
        """Danbooru parquet 검색"""
        try:
            if isinstance(query_json, str):
                q = json.loads(query_json)
            else:
                q = query_json
            ratings = q.get('ratings', ['g'])
            queries = q.get('queries', {})
            excludes = q.get('excludes', {})

            from workers.search_worker import PandasSearchWorker
            from config import PARQUET_DIR

            self._search_worker = PandasSearchWorker(PARQUET_DIR, ratings, queries, excludes)
            self._search_worker.results_ready.connect(self._on_search_results)
            self._search_worker.start()
            self.searchStatus.emit('검색 중...')
        except Exception as e:
            self.searchResultsReady.emit(json.dumps({'error': str(e)}))

    def _on_search_results(self, results, total_count):
        """검색 결과 수신 → Vue로 전달"""
        try:
            out = []
            if hasattr(results, 'iterrows'):
                for _, row in results.iterrows():
                    out.append({
                        'copyright': str(row.get('tag_string_copyright', '')),
                        'character': str(row.get('tag_string_character', '')),
                        'artist': str(row.get('tag_string_artist', '')),
                        'general': str(row.get('tag_string_general', '')),
                        'rating': str(row.get('rating', '')),
                    })
            self.searchResultsReady.emit(json.dumps(out))
            self.searchStatus.emit(f'{len(out)}개 결과 (전체 {total_count}개)')
        except Exception as e:
            self.searchResultsReady.emit(json.dumps({'error': str(e)}))

    @pyqtSlot(str, result=str)
    def loadImageBase64(self, filepath: str) -> str:
        """이미지를 base64로 반환"""
        import base64, os
        if not os.path.exists(filepath):
            return ''
        with open(filepath, 'rb') as f:
            data = f.read()
        ext = os.path.splitext(filepath)[1].lower()
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(ext, 'image/png')
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    @pyqtSlot(result=str)
    def getUpscalers(self) -> str:
        """API에서 업스케일러 목록 반환"""
        try:
            from backends import get_backend
            backend = get_backend()
            if backend:
                import requests
                r = requests.get(f"{backend.api_url}/sdapi/v1/upscalers", timeout=5)
                if r.status_code == 200:
                    return json.dumps([u['name'] for u in r.json()])
        except Exception:
            pass
        return json.dumps([])

    @pyqtSlot(str, str, result=str)
    def saveImageExif(self, filepath: str, new_params: str) -> str:
        """이미지의 PNG 메타데이터(parameters)를 수정하여 저장"""
        try:
            import os
            from PIL import Image as PILImage
            from PIL.PngImagePlugin import PngInfo
            if not filepath or not os.path.exists(filepath):
                return json.dumps({'error': '파일을 찾을 수 없습니다'})
            if not filepath.lower().endswith('.png'):
                return json.dumps({'error': 'PNG 파일만 메타데이터 수정 가능'})
            img = PILImage.open(filepath)
            meta = PngInfo()
            meta.add_text("parameters", new_params)
            # 기존 메타데이터 중 parameters 외 보존
            for k, v in img.info.items():
                if k != "parameters" and isinstance(v, str):
                    meta.add_text(k, v)
            img.save(filepath, pnginfo=meta)
            return json.dumps({'ok': True})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, str, result=str)
    def renameFile(self, filepath: str, new_name: str) -> str:
        """파일 이름 변경"""
        try:
            import os
            if not os.path.exists(filepath):
                return json.dumps({'error': '파일을 찾을 수 없습니다'})
            dir_path = os.path.dirname(filepath)
            ext = os.path.splitext(filepath)[1]
            if not new_name.endswith(ext):
                new_name += ext
            new_path = os.path.join(dir_path, new_name)
            os.rename(filepath, new_path)
            return json.dumps({'ok': True, 'new_path': new_path.replace('\\', '/')})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, int, int, result=str)
    def getEdgeMap(self, image_path: str, canny_low: int, canny_high: int) -> str:
        """Canny edge detection → base64 PNG (자석 올가미용)"""
        try:
            import cv2, numpy as np, base64, os
            from io import BytesIO
            from PIL import Image as PILImage
            clean = image_path.replace('file:///', '').replace('/', os.sep)
            img = cv2.imread(clean)
            if img is None:
                return ''
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, canny_low, canny_high)
            pil = PILImage.fromarray(edges)
            buf = BytesIO()
            pil.save(buf, format='PNG')
            return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        except Exception:
            return ''

    @pyqtSlot(result=str)
    def getYoloModelLabel(self) -> str:
        """YOLO 모델 라벨 반환"""
        try:
            import os
            from tabs.editor.mosaic_panel import _load_yolo_model_paths
            paths = _load_yolo_model_paths()
            if paths:
                return ", ".join([os.path.basename(p) for p in paths])
        except Exception:
            pass
        return "No Model Loaded"

    @pyqtSlot(str, result=str)
    def getTagSuggestions(self, prefix: str) -> str:
        """태그 자동완성 후보 반환"""
        try:
            from utils.tag_completer import get_tag_completer
            completer = get_tag_completer()
            suggestions = completer.get_suggestions(prefix, max_results=10)
            return json.dumps(suggestions)
        except Exception:
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def generateXYZCombinations(self, axes_json: str) -> str:
        """XYZ 축 데이터로 조합 생성"""
        try:
            import itertools
            if isinstance(axes_json, str):
                axes = json.loads(axes_json)
            else:
                axes = axes_json
            if not axes:
                return json.dumps([])
            value_lists = [a.get('values', []) for a in axes]
            types = [a.get('type', '') for a in axes]
            combos = list(itertools.product(*value_lists))
            result = []
            for combo in combos:
                item = {}
                for i, val in enumerate(combo):
                    item[types[i]] = val
                result.append(item)
            return json.dumps({'combinations': result, 'count': len(result)})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, str, str, result=str)
    def processBatchFile(self, filepath: str, operation: str, params_json: str) -> str:
        """단일 파일 배치 처리"""
        try:
            import cv2
            import numpy as np
            import os
            if isinstance(params_json, str):
                params = json.loads(params_json) if params_json else {}
            else:
                params = params_json
            img = cv2.imread(filepath)
            if img is None:
                return json.dumps({'error': f'파일 읽기 실패: {filepath}'})

            if operation == 'resize':
                w = int(params.get('width', img.shape[1]))
                h = int(params.get('height', img.shape[0]))
                img = cv2.resize(img, (w, h))
            elif operation == 'grayscale':
                img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)

            out_dir = os.path.join(os.path.dirname(filepath), 'batch_output')
            os.makedirs(out_dir, exist_ok=True)
            fmt = params.get('format', 'PNG').lower()
            ext = {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}.get(fmt, '.png')
            out_path = os.path.join(out_dir, os.path.splitext(os.path.basename(filepath))[0] + ext)
            cv2.imwrite(out_path, img)
            return json.dumps({'path': out_path.replace('\\', '/')})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, result=str)
    def getImageExif(self, filepath: str) -> str:
        """이미지의 EXIF 반환"""
        try:
            from PIL import Image
            import os
            img = Image.open(filepath)
            info = {}
            raw = img.info.get('parameters', img.info.get('prompt', ''))
            info['raw'] = raw
            info['path'] = filepath.replace('\\', '/')
            info['filename'] = os.path.basename(filepath)
            info['size'] = f"{img.width} × {img.height}"
            if raw and 'Steps:' in raw:
                parts = raw.split('\nNegative prompt: ')
                info['prompt'] = parts[0].strip()
                if len(parts) > 1:
                    sub = parts[1].split('\nSteps: ')
                    info['negative'] = sub[0].strip()
            return json.dumps(info)
        except Exception as e:
            return json.dumps({'error': str(e), 'path': filepath})

    @pyqtSlot(str, result=str)
    def getPngInfo(self, filepath: str) -> str:
        """PNG 메타데이터 반환"""
        try:
            from PIL import Image
            img = Image.open(filepath)
            info = {}
            if 'parameters' in img.info: info['parameters'] = img.info['parameters']
            elif 'prompt' in img.info: info['prompt'] = img.info['prompt']
            return json.dumps(info)
        except Exception as e:
            return json.dumps({'error': str(e)})
