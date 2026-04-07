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
    galleryFolderLoaded = pyqtSignal(str)  # folder path
    exifLoaded = pyqtSignal(str)           # JSON {path, exif}
    inpaintImageLoaded = pyqtSignal(str)   # file path
    searchStatus = pyqtSignal(str)         # status message

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
    def onWidgetChanged(self, widget_id: str, value: str):
        """Vue에서 사용자가 위젯 값을 변경했을 때"""
        proxy = self._proxies.get(widget_id)
        if proxy:
            proxy._on_vue_changed(value)

    @pyqtSlot(str, str)
    def onAction(self, action: str, payload_json: str):
        """Vue에서 버튼 클릭 등 액션 요청"""
        if self._action_handler:
            try:
                payload = json.loads(payload_json) if payload_json else {}
                self._action_handler(action, payload)
            except Exception as e:
                print(f"[VueBridge] Action error: {action} - {e}")

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
            params = json.loads(params_json) if params_json else {}
            img = cv2.imread(image_path)
            if img is None:
                return json.dumps({'error': '이미지를 읽을 수 없습니다'})

            # 선택 영역 추출
            sel = params.get('selection')
            if sel:
                x1, y1 = int(sel.get('x', 0)), int(sel.get('y', 0))
                x2 = x1 + int(sel.get('w', img.shape[1]))
                y2 = y1 + int(sel.get('h', img.shape[0]))
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
            else:
                x1, y1, x2, y2 = 0, 0, img.shape[1], img.shape[0]

            roi = img[y1:y2, x1:x2]

            if operation == 'mosaic':
                strength = params.get('strength', 20)
                h_r, w_r = roi.shape[:2]
                small = cv2.resize(roi, (max(1, w_r // strength), max(1, h_r // strength)))
                roi = cv2.resize(small, (w_r, h_r), interpolation=cv2.INTER_NEAREST)
                img[y1:y2, x1:x2] = roi
            elif operation == 'censor_bar':
                img[y1:y2, x1:x2] = 0  # 검은색
            elif operation == 'blur':
                strength = params.get('strength', 15)
                k = max(1, strength) | 1
                roi = cv2.GaussianBlur(roi, (k, k), 0)
                img[y1:y2, x1:x2] = roi
            elif operation == 'rotate_cw':
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            elif operation == 'rotate_ccw':
                img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif operation == 'flip_h':
                img = cv2.flip(img, 1)
            elif operation == 'flip_v':
                img = cv2.flip(img, 0)
            elif operation == 'grayscale':
                img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            elif operation == 'sepia':
                kernel = np.array([[0.272, 0.534, 0.131],
                                   [0.349, 0.686, 0.168],
                                   [0.393, 0.769, 0.189]])
                img = cv2.transform(img, kernel)
                img = np.clip(img, 0, 255).astype(np.uint8)
            elif operation == 'sharpen':
                kernel = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
                img = cv2.filter2D(img, -1, kernel)
            elif operation == 'brightness':
                value = params.get('value', 0)
                img = cv2.convertScaleAbs(img, alpha=1, beta=value)
            elif operation == 'contrast':
                value = params.get('value', 1.0)
                img = cv2.convertScaleAbs(img, alpha=value, beta=0)
            elif operation == 'resize':
                w = params.get('width', img.shape[1])
                h = params.get('height', img.shape[0])
                img = cv2.resize(img, (int(w), int(h)))
            elif operation == 'color_adjust':
                b_val = params.get('brightness', 0)
                c_val = params.get('contrast', 0)
                s_val = params.get('saturation', 0)
                if b_val != 0:
                    img = cv2.convertScaleAbs(img, alpha=1, beta=b_val)
                if c_val != 0:
                    factor = (100 + c_val) / 100.0
                    img = cv2.convertScaleAbs(img, alpha=factor, beta=0)
                if s_val != 0:
                    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
                    hsv[:,:,1] *= (100 + s_val) / 100.0
                    hsv[:,:,1] = np.clip(hsv[:,:,1], 0, 255)
                    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
            elif operation == 'crop':
                x1 = params.get('x1', 0)
                y1 = params.get('y1', 0)
                x2 = params.get('x2', img.shape[1])
                y2 = params.get('y2', img.shape[0])
                img = img[int(y1):int(y2), int(x1):int(x2)]

            # 결과 저장 (에디터 전용 폴더 — 히스토리에 안 나타남)
            import os, time, random as rnd
            out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'image_cache', 'editor_temp')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"edited_{int(time.time())}_{rnd.randint(100,999)}.png")
            cv2.imwrite(out_path, img)
            return json.dumps({'path': out_path.replace('\\', '/'), 'width': img.shape[1], 'height': img.shape[0]})
        except Exception as e:
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
        for f in sorted(os.listdir(target), key=lambda x: os.path.getmtime(os.path.join(target, x)), reverse=True):
            if f.lower().endswith(exts):
                fp = os.path.join(target, f).replace('\\', '/')
                files.append(fp)
            if len(files) >= 200:
                break
        return json.dumps(files)

    # ── PNG Info ──

    @pyqtSlot(result=str)
    def getFavorites(self) -> str:
        """즐겨찾기 목록 반환"""
        import os
        from config import FAVORITES_FILE
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return json.dumps([])

    searchResultsReady = pyqtSignal(str)  # JSON results

    @pyqtSlot(str)
    def searchDanbooru(self, query_json: str):
        """Danbooru parquet 검색 (비동기 — 결과는 searchResultsReady 시그널)"""
        try:
            q = json.loads(query_json)
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
                for _, row in results.head(200).iterrows():
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
        mime = {'png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(ext, 'image/png')
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

    @pyqtSlot(str, result=str)
    def getImageExif(self, filepath: str) -> str:
        """이미지의 EXIF/생성정보를 상세 JSON으로 반환"""
        try:
            from PIL import Image
            import os
            img = Image.open(filepath)
            info = {}
            raw = ''
            if 'parameters' in img.info:
                raw = img.info['parameters']
            elif 'prompt' in img.info:
                raw = img.info.get('prompt', '')

            info['raw'] = raw
            info['path'] = filepath.replace('\\', '/')
            info['filename'] = os.path.basename(filepath)
            info['size'] = f"{img.width} × {img.height}"
            info['format'] = img.format or 'Unknown'
            info['filesize'] = f"{os.path.getsize(filepath) / 1024:.1f} KB"

            # WebUI 파라미터 파싱
            if raw and 'Steps:' in raw:
                parts = raw.split('\nNegative prompt: ')
                info['prompt'] = parts[0].strip()
                if len(parts) > 1:
                    sub = parts[1].split('\nSteps: ')
                    info['negative'] = sub[0].strip()
                    if len(sub) > 1:
                        info['params_line'] = 'Steps: ' + sub[1].strip()
            return json.dumps(info)
        except Exception as e:
            return json.dumps({'error': str(e), 'path': filepath})

    @pyqtSlot(str, result=str)
    def getPngInfo(self, filepath: str) -> str:
        """이미지의 PNG 메타데이터 반환"""
        try:
            from PIL import Image
            img = Image.open(filepath)
            info = {}
            if 'parameters' in img.info:
                info['parameters'] = img.info['parameters']
            elif 'prompt' in img.info:
                info['prompt'] = img.info['prompt']
                if 'workflow' in img.info:
                    info['workflow'] = img.info['workflow']
            return json.dumps(info)
        except Exception as e:
            return json.dumps({'error': str(e)})
