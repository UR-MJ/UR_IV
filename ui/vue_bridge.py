# ui/vue_bridge.py
"""
PyQt6 ↔ Vue 통신 브릿지 (QWebChannel)
위젯 프록시 값 동기화 + 액션 디스패치 + 이미지 생성 이벤트
"""
import json
import logging
import os
import threading
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from core.path_safety import safe_input_path as _normalize_vue_path  # noqa: F401

logger = logging.getLogger(__name__)


class VueBridge(QObject):
    """Vue 프론트엔드와 통신하는 중앙 브릿지"""

    # ── Python → Vue 시그널 ──
    imageGenerated = pyqtSignal(str)
    generationStarted = pyqtSignal()
    generationError = pyqtSignal(str)

    editorImageLoaded = pyqtSignal(str)   # file path
    captionFilesSelected = pyqtSignal(str)  # JSON [path] — 캡션 대상 이미지
    captionProgress = pyqtSignal(str)       # JSON {index,total,path,caption,error}
    captionDone = pyqtSignal(str)           # JSON {total,ok,failed}
    captionOutDirSelected = pyqtSignal(str)  # 캡션 저장 폴더 경로
    i2iImageLoaded = pyqtSignal(str)     # file path
    galleryFolderLoaded = pyqtSignal(str)  # folder path
    inpaintImageLoaded = pyqtSignal(str)   # file path (PngInfo + InpaintView 공용)
    searchStatus = pyqtSignal(str)         # status message

    loraInserted = pyqtSignal(str)       # JSON {name, weight}
    loraStackLoaded = pyqtSignal(str)    # JSON [{name, weight, enabled, triggerWords}]
    yoloModelUpdated = pyqtSignal(str)   # model label text
    condRulesLoaded = pyqtSignal(str)    # JSON {positive, negative}
    batchFilesSelected = pyqtSignal(str) # JSON [paths]
    ollamaResult = pyqtSignal(str)       # JSON {tags, mode} or {error}
    genNlResult = pyqtSignal(str)        # JSON {tags, mode} or {error} — 생성 시 태그→자연어 전용 채널
    globalWeightsLoaded = pyqtSignal(str) # JSON [{tag, weight}]
    uiPrefsLoaded = pyqtSignal(str)      # JSON {tagBlockMode, ...}
    compareImageLoaded = pyqtSignal(str) # JSON {slot, path}
    galleryImagesReady = pyqtSignal(str) # JSON {folder, files}
    upscalersReady = pyqtSignal(str)      # JSON [name]
    ollamaModelsReady = pyqtSignal(str)   # JSON {url, models}
    adetailerModelsReady = pyqtSignal(str) # JSON [name]
    queueItemAdded = pyqtSignal(str)     # JSON {prompt, ...}
    queueCompleted = pyqtSignal(str)     # JSON {total}
    showNotification = pyqtSignal(str, str)  # (type: success|error|info, message)
    adetailerResult = pyqtSignal(str)       # JSON {before, after, output_path} or {error}
    adetailerProgress = pyqtSignal(int, int) # (current, total)
    sam3Result = pyqtSignal(str)            # JSON {before, after, output_path} or {error}
    sam3Progress = pyqtSignal(int, int)     # (current, total)
    eventSearchProgress = pyqtSignal(int, int) # (current, total)
    automationStatus = pyqtSignal(str)        # JSON {running, count, waiting}
    automationSettingsLoaded = pyqtSignal(str)  # JSON {mode, limit, repeat, delay, allowDupes, maxRetries} — PR 9 mode-aware
    instantWildcardsList = pyqtSignal(str)      # JSON [{name, lines: [...]}] — PR 8
    promptOrderLoaded = pyqtSignal(str)         # JSON [{key, label}] — 사용자 지정 섹션 순서
    workflowProfilesList = pyqtSignal(str)      # JSON [{name, created_at, model, vae}]
    eventImportResults = pyqtSignal(str)      # JSON event list

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
        self._async_lookup_inflight = set()
        self._async_lookup_lock = threading.Lock()
        self.adetailerModelsReady.connect(self._apply_adetailer_models_json)

    def _run_async_lookup(self, key, loader, signal):
        """GUI 스레드를 막는 조회를 중복 없이 백그라운드에서 실행한다."""
        with self._async_lookup_lock:
            if key in self._async_lookup_inflight:
                return
            self._async_lookup_inflight.add(key)

        def _work():
            try:
                signal.emit(loader())
            except Exception as e:
                logger.warning("async lookup failed (%s): %s", key, e)
            finally:
                with self._async_lookup_lock:
                    self._async_lookup_inflight.discard(key)

        threading.Thread(target=_work, daemon=True, name=f"vue-{key}").start()

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

    # ── Editor ──

    editorResult = pyqtSignal(str)  # 에디터 비동기 처리 결과 JSON (path|mask_base64|error + operation, job_id)

    @pyqtSlot(str, str, str, result=str)
    def editorProcess(self, image_path: str, operation: str, params_json: str) -> str:
        """에디터 이미지 처리 — 무거운 작업(YOLO/SAM/rembg/OpenCV)을 백그라운드 스레드로.

        동기 슬롯으로 GUI 스레드에서 전부 돌면 클릭마다 창 전체가 수~수십 초 멈춤
        (YOLO 로드+추론, SAM 체크포인트 로드, alpha_matting rembg).
        즉시 {'started': True, 'job_id': n}을 반환하고, 완료 시 editorResult
        시그널로 결과를 보낸다 (generateThumbnails / startCaptioning과 동일 패턴).
        """
        clean_path = _normalize_vue_path(image_path)
        if not clean_path:
            logger.warning("[Editor] invalid or forbidden path")
            return json.dumps({'error': '유효하지 않은 이미지 경로입니다'})

        # params가 객체로 올 수도 있고 JSON 문자열로 올 수도 있음
        try:
            if isinstance(params_json, str):
                params = json.loads(params_json) if params_json else {}
            else:
                params = params_json or {}
            if not isinstance(params, dict):
                params = {}
        except Exception as e:
            return json.dumps({'error': f'잘못된 파라미터: {e}'})

        self._editor_job_seq = getattr(self, '_editor_job_seq', 0) + 1
        job_id = self._editor_job_seq

        import threading

        def _work():
            result_json = self._editor_process_impl(clean_path, operation, params)
            try:
                payload = json.loads(result_json)
            except Exception:
                payload = {'error': '에디터 내부 오류'}
            payload['job_id'] = job_id
            payload['operation'] = operation
            try:
                # 비-Qt 스레드 emit은 queued connection이라 안전
                self.editorResult.emit(json.dumps(payload))
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()
        return json.dumps({'started': True, 'job_id': job_id})

    def _editor_process_impl(self, clean_path: str, operation: str, params: dict) -> str:
        """editorProcess 본체 — 워커 스레드에서 실행. 위젯 직접 접근 금지(시그널 emit만)."""
        try:
            import cv2
            import numpy as np

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
                    from tabs.editor.mosaic_panel import _load_yolo_model_paths, _is_sam_file
                    model_paths = _load_yolo_model_paths()
                    if not model_paths:
                        return json.dumps({'error': 'YOLO 모델을 먼저 추가하세요 (+ADD .PT)'})
                    conf = float(params.get('confidence', 0.25))
                    from ultralytics import YOLO
                    h_img, w_img = img.shape[:2]
                    combined_mask = np.zeros((h_img, w_img), dtype=np.uint8)
                    detect_count = 0
                    yolo_boxes = []
                    has_seg_mask = False
                    loaded_names, failed = [], []

                    # 단일 패스: 모델당 1회만 로드 → mask + bbox 동시 수집
                    for mp in model_paths:
                        if not os.path.exists(mp):
                            failed.append((mp, 'not found'))
                            continue
                        if _is_sam_file(mp):
                            print(f"[YOLO] Skip SAM model (not a detector): {os.path.basename(mp)}")
                            continue
                        try:
                            model = YOLO(mp)
                        except Exception as me:
                            print(f"[YOLO] Model load failed: {mp} — {me}")
                            failed.append((os.path.basename(mp), str(me)))
                            continue
                        loaded_names.append(os.path.basename(mp))
                        try:
                            results = model(img, conf=conf, verbose=False)
                        except Exception as ie:
                            print(f"[YOLO] Inference failed: {mp} — {ie}")
                            failed.append((os.path.basename(mp), f'inference: {ie}'))
                            continue
                        for r in results:
                            # 세그먼트 마스크 (성기 형태 정밀)
                            if r.masks is not None:
                                has_seg_mask = True
                                for m_tensor in r.masks.data:
                                    m_np = m_tensor.cpu().numpy().astype(np.float32)
                                    m_resized = cv2.resize(m_np, (w_img, h_img), interpolation=cv2.INTER_LINEAR)
                                    combined_mask[m_resized > 0.3] = 255
                                    detect_count += 1
                            # 박스 (SAM 정밀화 입력 + 마스크 폴백)
                            if r.boxes is not None:
                                for box in r.boxes.xyxy:
                                    bx1, by1, bx2, by2 = map(int, box.tolist())
                                    bx1, by1 = max(0, bx1), max(0, by1)
                                    bx2, by2 = min(w_img, bx2), min(h_img, by2)
                                    if bx2 > bx1 and by2 > by1:
                                        yolo_boxes.append((bx1, by1, bx2, by2))
                                        if r.masks is None:
                                            combined_mask[by1:by2, bx1:bx2] = 255
                                            detect_count += 1

                    if not loaded_names:
                        # 등록된 모든 모델이 실패한 경우 명확한 에러
                        msg = '; '.join(f'{os.path.basename(n)}: {e}' for n, e in failed) or '모든 YOLO 모델 로드 실패'
                        try:
                            self.showNotification.emit('error', f'YOLO 모델 로드 실패 — {msg[:200]}')
                        except Exception:
                            pass
                        return json.dumps({'error': f'YOLO 모델 로드 실패 — {msg}'})

                    # 일부만 실패한 경우 경고
                    if failed:
                        fail_msg = ', '.join(os.path.basename(n) for n, _e in failed[:3])
                        if len(failed) > 3:
                            fail_msg += f' 외 {len(failed) - 3}개'
                        try:
                            self.showNotification.emit('warning', f'YOLO 일부 모델 실패: {fail_msg}')
                        except Exception:
                            pass

                    print(f"[YOLO] Loaded {loaded_names} → {detect_count} regions, {len(yolo_boxes)} boxes, seg_mask={has_seg_mask}")

                    # SAM 정밀 마스킹 — 사용자가 모델 선택 가능
                    sam_choice = str(params.get('sam_model', 'auto')).lower()
                    if yolo_boxes and sam_choice != 'off':
                        try:
                            from core.sam_refiner import refine_boxes_with_sam, find_sam_model
                            from tabs.editor.mosaic_panel import get_editor_models_dir
                            models_dir = get_editor_models_dir()
                            sam_path, sam_type = find_sam_model(models_dir, prefer_type=sam_choice)
                            print(f"[SAM] choice={sam_choice}, models_dir={models_dir}, found={sam_path}, type={sam_type}, has_seg={has_seg_mask}")

                            if has_seg_mask and sam_type != 'sam3':
                                # YOLO seg 마스크가 이미 있고 SAM3가 아니면 정밀화 생략
                                print("[SAM] YOLO seg mask available, skipping SAM")
                            elif sam_path:
                                # SAM3 전용: 마스크에서 빼고 싶은 영역의 텍스트 프롬프트
                                #   예: 'face' → 얼굴 영역을 검출해서 최종 마스크에서 빼기
                                excl_prompt = params.get('exclude_prompt') or params.get('excludePrompt')
                                excl_prompt = str(excl_prompt).strip() if excl_prompt else None
                                if excl_prompt and sam_type == 'sam3':
                                    print(f"[SAM3] exclude prompt requested: '{excl_prompt}'")
                                # 사용자 알림 콜백 — SAM3 exclude 안전장치 발동 시 토스트로 전달
                                def _sam_notify(level, message):
                                    try:
                                        self.showNotification.emit(level, message)
                                    except Exception:
                                        pass
                                sam_mask = refine_boxes_with_sam(
                                    img, yolo_boxes, models_dir,
                                    sam_model_path=sam_path, sam_type=sam_type,
                                    yolo_model_paths=model_paths,
                                    exclude_prompt=excl_prompt,
                                    notify=_sam_notify,
                                )
                                if sam_mask.any():
                                    combined_mask = sam_mask
                                    pixel_count = int(sam_mask.sum() / 255)
                                    print(f"[SAM] ✓ Refined mask applied ({sam_type}, {len(yolo_boxes)} boxes → {pixel_count} pixels)")
                                else:
                                    print("[SAM] No mask generated, using YOLO bbox")
                            else:
                                if sam_choice != 'auto':
                                    print(f"[SAM] '{sam_choice}' 모델이 editor_models/에 없음 — bbox 사용")
                                else:
                                    print(f"[SAM] No SAM model in {models_dir}, using YOLO bbox")
                        except ImportError as ie:
                            print(f"[SAM] Import error: {ie}")
                            try:
                                self.showNotification.emit('warning', f'SAM 라이브러리 미설치 — bbox 마스크 사용 ({type(ie).__name__})')
                            except Exception:
                                pass
                        except Exception as sam_e:
                            import traceback
                            print(f"[SAM] Error: {sam_e}")
                            traceback.print_exc()
                            try:
                                self.showNotification.emit('error', f'SAM 정밀화 실패: {sam_e}')
                            except Exception:
                                pass

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
                    from core.error_handler import handle_error
                    handle_error('E100', 'Auto Censor', e)
                    return json.dumps({'error': f'[E100] Auto censor 실패: {e}'})

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
                except Exception:
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
                    quality = params.get('quality', 'balanced')
                    pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

                    rm_kwargs = {}
                    if quality in ('balanced', 'quality'):
                        rm_kwargs['alpha_matting'] = True
                        rm_kwargs['alpha_matting_foreground_threshold'] = 240 if quality == 'balanced' else 270
                        rm_kwargs['alpha_matting_background_threshold'] = 10 if quality == 'balanced' else 20
                        rm_kwargs['alpha_matting_erode_size'] = 10 if quality == 'balanced' else 15

                    result = remove(pil_img, **rm_kwargs)
                    img = cv2.cvtColor(np.array(result), cv2.COLOR_RGBA2BGRA)

                    # Quality 모드: 엣지 정제
                    if quality == 'quality':
                        try:
                            from core.edge_refiner import refine_alpha
                            img = refine_alpha(img)
                        except Exception as re:
                            print(f"[Editor] Edge refine skipped: {re}")
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
            from core.error_handler import handle_error
            handle_error('E040', f'Editor: {operation}', e)
            return json.dumps({'error': f'[E040] {operation}: {e}'})

    # ── 갤러리 ──

    @pyqtSlot(result=str)
    def getLastGalleryFolder(self) -> str:
        """마지막 Gallery 폴더 경로 반환"""
        import os
        cfg = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'gallery_last_folder.txt')
        try:
            if os.path.exists(cfg):
                with open(cfg, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logger.warning("getLastGalleryFolder failed: %s", e)
        from config import OUTPUT_DIR
        return OUTPUT_DIR

    def _save_gallery_folder(self, folder: str):
        import os
        cfg = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'gallery_last_folder.txt')
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, 'w') as f:
            f.write(folder)

    def _gallery_images_payload(self, folder: str) -> str:
        """scandir의 stat 캐시를 이용해 날짜순 이미지 목록을 만든다."""
        import os
        from config import OUTPUT_DIR
        target = folder if folder else OUTPUT_DIR
        if not os.path.isdir(target):
            return json.dumps({'folder': folder, 'files': []})
        exts = ('.png', '.jpg', '.jpeg', '.webp')
        entries = []
        try:
            with os.scandir(target) as scan:
                for entry in scan:
                    if entry.is_file() and entry.name.lower().endswith(exts):
                        try:
                            mtime = entry.stat().st_mtime
                        except OSError:
                            mtime = 0
                        entries.append((mtime, entry.path.replace('\\', '/')))
            entries.sort(key=lambda item: item[0], reverse=True)
        except Exception as e:
            logger.warning("getGalleryImages failed (%s): %s", target, e)
        return json.dumps({'folder': folder, 'files': [path for _, path in entries]})

    @pyqtSlot(str, result=str)
    def getGalleryImages(self, folder: str) -> str:
        """하위호환 동기 API. 신규 Vue 코드는 requestGalleryImages를 사용한다."""
        try:
            return json.dumps(json.loads(self._gallery_images_payload(folder))['files'])
        except Exception:
            return '[]'

    @pyqtSlot(str)
    def requestGalleryImages(self, folder: str):
        """폴더 스캔/정렬을 백그라운드에서 수행해 GUI 멈춤을 방지한다."""
        key = f"gallery:{folder or '<default>'}"
        self._run_async_lookup(
            key,
            lambda: self._gallery_images_payload(folder),
            self.galleryImagesReady,
        )

    @pyqtSlot(result=str)
    def getFavorites(self) -> str:
        """즐겨찾기 목록 반환"""
        import os
        from config import FAVORITES_FILE
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        return json.dumps([])

    thumbnailReady = pyqtSignal(str)   # JSON {path, thumb} — 썸네일 1건 생성/조회 완료 통지

    @pyqtSlot(str, int)
    def generateThumbnails(self, paths_json: str, width: int = 256):
        """주어진 이미지 경로들의 썸네일을 백그라운드 스레드에서 생성/캐싱하고,
        각 건마다 thumbnailReady 시그널로 통지 (GUI 스레드 블로킹 방지).
        캐시: image_cache/thumbs/<sha1>.jpg"""
        try:
            paths = json.loads(paths_json) if paths_json else []
        except Exception:
            return
        if not paths:
            return
        import threading

        def _work():
            import hashlib
            base = os.path.dirname(os.path.dirname(__file__))
            thumb_dir = os.path.join(base, 'image_cache', 'thumbs')
            try:
                os.makedirs(thumb_dir, exist_ok=True)
            except Exception:
                return
            for p in paths:
                thumb_url = ''
                try:
                    norm = os.path.normpath(p)
                    h = hashlib.sha1(f"{norm}@{width}".encode('utf-8')).hexdigest()
                    tp = os.path.join(thumb_dir, f"{h}.jpg")
                    if not os.path.exists(tp):
                        if os.path.exists(p):
                            from PIL import Image, ImageOps
                            im = Image.open(p)
                            try:
                                im = ImageOps.exif_transpose(im)
                            except Exception:
                                pass
                            im = im.convert('RGB')
                            im.thumbnail((width, width), Image.Resampling.LANCZOS)
                            im.save(tp, 'JPEG', quality=80)
                    if os.path.exists(tp):
                        thumb_url = 'file:///' + tp.replace('\\', '/')
                except Exception:
                    thumb_url = ''
                try:
                    self.thumbnailReady.emit(json.dumps({'path': p, 'thumb': thumb_url}))
                except Exception:
                    pass
        threading.Thread(target=_work, daemon=True).start()

    searchResultsReady = pyqtSignal(str)   # JSON results
    queueUpdated = pyqtSignal(str)         # JSON queue state
    eventSearchResults = pyqtSignal(str)   # JSON event results
    generationProgress = pyqtSignal(int, int)  # current, total steps

    @pyqtSlot(str)
    def searchDanbooru(self, query_json: str):
        """Danbooru parquet 검색
        query JSON 구조:
          ratings: ['g', 's', ...]
          queries: { character: '...', copyright: '...', ... }    # 포함 조건
          excludes: { character: '...', ... }                     # 제외 조건
          combine_mode: 'and' | 'or'  (필드 간 결합 — 기본 'and')
          dataset_year: '2025' | '2026'  (단일 선택 — 기본 '2026')
        """
        try:
            if isinstance(query_json, str):
                q = json.loads(query_json)
            else:
                q = query_json
            ratings = q.get('ratings', ['g'])
            queries = q.get('queries', {})
            excludes = q.get('excludes', {})
            combine_mode = str(q.get('combine_mode', 'and')).lower()
            if combine_mode not in ('and', 'or'):
                combine_mode = 'and'

            from workers.search_worker import PandasSearchWorker
            from config import PARQUET_DIR

            dataset_year = str(q.get('dataset_year', PandasSearchWorker.DEFAULT_YEAR))
            if dataset_year not in PandasSearchWorker.AVAILABLE_YEARS:
                dataset_year = PandasSearchWorker.DEFAULT_YEAR

            # 결과 cap 비활성화 — 사용자가 "무제한" 모드 선택 시
            self._disable_result_cap = bool(q.get('disable_result_cap', False))

            # 이전 검색 워커 정리 — 덮어쓰기만 하면 stale 결과가 새 결과를 덮거나
            # 실행 중 QThread 파괴로 크래시 가능 (ollamaEnhance와 동일 패턴)
            prev = getattr(self, '_search_worker', None)
            if prev is not None and prev.isRunning():
                try:
                    prev.results_ready.disconnect(self._on_search_results)
                except TypeError:
                    pass
                prev.stop()
                if not prev.wait(1000):
                    # 아직 도는 중 — 참조를 보관해 가비지 파괴 크래시 방지, 종료 시 자동 제거
                    if not hasattr(self, '_stale_search_workers'):
                        self._stale_search_workers = []
                    self._stale_search_workers.append(prev)
                    prev.finished.connect(
                        lambda w=prev: self._stale_search_workers.remove(w)
                        if w in getattr(self, '_stale_search_workers', []) else None)

            self._search_worker = PandasSearchWorker(
                PARQUET_DIR, ratings, queries, excludes,
                combine_mode=combine_mode,
                dataset_year=dataset_year,
                result_cap=None if self._disable_result_cap else 500_000,
            )
            self._search_worker.results_ready.connect(self._on_search_results)
            self._search_worker.start()
            cap_note = " · cap OFF" if self._disable_result_cap else ""
            self.searchStatus.emit(
                f"검색 중... ({dataset_year} · {combine_mode.upper()}{cap_note})"
            )
        except Exception as e:
            self.searchResultsReady.emit(json.dumps({'error': str(e)}))

    def _on_search_results(self, results, total_count):
        """검색 결과 수신 → Vue 전달 + Python filtered_results 업데이트

        BUG FIX: search_worker는 to_dict('records')로 list[dict]를 emit하지만
        과거 코드가 DataFrame 가정으로 hasattr(iterrows)만 체크 → list 무시 → 0건.
        list / DataFrame 양쪽 지원 + 컬럼명도 두 스키마 (tag_string_* / *) 호환.
        """
        # 순서 역전 차단 — 현재 워커가 아닌(이전 검색의) 늦은 시그널은 무시
        sender = self.sender()
        if sender is not None and sender is not getattr(self, '_search_worker', None):
            print("[Search] stale worker result ignored")
            return
        try:
            import random as _rnd
            out = []

            def _pick(row, primary, alt):
                """tag_string_X 우선, 없으면 X — 양쪽 parquet 스키마 호환"""
                v = row.get(primary)
                if v is None or v == '':
                    v = row.get(alt, '')
                return str(v) if v is not None else ''

            def _dim(row, key):
                """image_width/height → int 또는 None (없으면 자동 해상도 폴백)"""
                v = row.get(key)
                try:
                    if v is None or v == '':
                        return None
                    iv = int(float(v))
                    return iv if iv > 0 else None
                except (ValueError, TypeError):
                    return None

            if isinstance(results, list):
                # 현재 워커 결과는 이 시점 이후 다른 소비자가 없으므로 기존 dict를
                # 정규화해 재사용한다. 수십만 행에서 동일 크기의 두 번째 list[dict]가
                # 동시에 존재하던 피크 메모리를 제거한다.
                out = results
                write_idx = 0
                for row in out:
                    if not isinstance(row, dict):
                        continue
                    copyright = _pick(row, 'tag_string_copyright', 'copyright')
                    character = _pick(row, 'tag_string_character', 'character')
                    artist = _pick(row, 'tag_string_artist', 'artist')
                    general = _pick(row, 'tag_string_general', 'general')
                    rating = str(row.get('rating') or '')
                    image_width = _dim(row, 'image_width')
                    image_height = _dim(row, 'image_height')
                    row.clear()
                    row['copyright'] = copyright
                    row['character'] = character
                    row['artist'] = artist
                    row['general'] = general
                    row['rating'] = rating
                    row['image_width'] = image_width
                    row['image_height'] = image_height
                    out[write_idx] = row
                    write_idx += 1
                if write_idx < len(out):
                    del out[write_idx:]
            elif hasattr(results, 'iterrows'):
                # 옛 형식 fallback: DataFrame
                for _, row in results.iterrows():
                    out.append({
                        'copyright': _pick(row, 'tag_string_copyright', 'copyright'),
                        'character': _pick(row, 'tag_string_character', 'character'),
                        'artist':    _pick(row, 'tag_string_artist',    'artist'),
                        'general':   _pick(row, 'tag_string_general',   'general'),
                        'rating':    str(row.get('rating') or ''),
                        'image_width':  _dim(row, 'image_width'),
                        'image_height': _dim(row, 'image_height'),
                    })
            else:
                print(f"[Search] _on_search_results: unknown type {type(results)}")

            print(f"[Search] _on_search_results: built {len(out):,} dicts from {type(results).__name__}")

            # 큰 결과셋 안전장치 — Vue에 너무 많이 보내면 JSON 직렬화/전송이 느려짐
            # 사용자가 "무제한" 토글로 끌 수 있음 (disable_result_cap)
            MAX_RESULTS_TO_VUE = 500_000
            disable_cap = getattr(self, '_disable_result_cap', False)
            if disable_cap:
                print(f"[Search] cap DISABLED — emitting all {len(out):,} rows (UI 느려질 수 있음)")
            elif len(out) > MAX_RESULTS_TO_VUE:
                print(f"[Search] capping {len(out):,} → {MAX_RESULTS_TO_VUE:,} (UI 부하 방지)")
                # 무작위 샘플링 (앞부분만 보내면 편향됨)
                _rnd.shuffle(out)
                out = out[:MAX_RESULTS_TO_VUE]

            # Vue로 전달
            self.searchResultsReady.emit(
                json.dumps(out, ensure_ascii=False, separators=(',', ':')))
            self.searchStatus.emit(f'{len(out):,}개 결과 (전체 {total_count:,}개)')

            # Python 메인 윈도우의 filtered_results도 업데이트 (랜덤 프롬프트용)
            main_win = self.parent()
            if main_win and hasattr(main_win, 'filtered_results'):
                main_win.filtered_results = out
                main_win.shuffled_prompt_deck = out.copy()
                _rnd.shuffle(main_win.shuffled_prompt_deck)
                # 새 검색 → 덱 진행도 초기화 저장 (옛 진행도 덮어쓰기)
                if hasattr(main_win, '_save_deck_state'):
                    main_win._save_deck_state()

            # ── 디스크 영속(단일 쓰기 경로): 재시작 시 자동 복원 → 자동화 즉시 사용 ──
            #   새 검색이므로 active=full 동일(전체). 디스크=영속 단일소스, localStorage(slim)=폴백.
            #   쓰기 로직은 generator_main._persist_search_results 한 곳으로 통일(드리프트 방지).
            if main_win and hasattr(main_win, '_persist_search_results'):
                main_win._persist_search_results(out, full=out)
                print(f"[Search] saved {len(out):,} rows to disk (single write path)")
            else:
                # 폴백: 메인 윈도우 없음(개발/단독) — 직접 기록
                try:
                    import os
                    from utils.atomic_json import atomic_write_json
                    cache_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
                    for name in ('last_search_results.json', 'last_full_results.json'):
                        atomic_write_json(os.path.join(cache_dir, name), out, indent=None)
                except Exception as e:
                    print(f"[Search] disk backup failed: {e}")
        except Exception as e:
            self.searchResultsReady.emit(json.dumps({'error': str(e)}))

    @pyqtSlot(result=str)
    def loadLastSearchResults(self) -> str:
        """디스크에서 마지막 검색 결과 로드 (Vue가 onMounted에서 호출)
        Returns: JSON string of list[dict] (빈 경우 '[]')
        """
        try:
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base_dir, 'config', 'last_search_results.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = f.read()
                # main_win.filtered_results 도 미리 복원해두면 자동화 즉시 사용 가능
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, list) and parsed:
                        main_win = self.parent()
                        if main_win and hasattr(main_win, 'filtered_results'):
                            import random as _rnd
                            main_win.filtered_results = parsed
                            # 저장된 덱 진행도 복원 ('얼마나 뽑았는지' 유지).
                            # 실패(파일 없음/풀 크기 변경)면 전체 셔플로 폴백.
                            if not (hasattr(main_win, '_restore_deck_state')
                                    and main_win._restore_deck_state()):
                                main_win.shuffled_prompt_deck = parsed.copy()
                                _rnd.shuffle(main_win.shuffled_prompt_deck)
                            print(f"[Search] restored {len(parsed):,} rows from disk → filtered_results")
                except Exception:
                    pass
                return data
        except Exception as e:
            print(f"[Search] loadLastSearchResults failed: {e}")
        return '[]'

    @pyqtSlot(result=str)
    def loadFullResults(self) -> str:
        """필터 적용 '전' 전체 검색 셋을 디스크에서 로드 (Vue가 '필터 해제' 베이스로 사용).
        last_full_results.json 우선, 없으면 last_search_results.json 폴백.
        (loadLastSearchResults와 달리 Python 덱/filtered_results는 건드리지 않음 —
        순수 조회.)"""
        try:
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for name in ('last_full_results.json', 'last_search_results.json'):
                path = os.path.join(base_dir, 'config', name)
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        return f.read()
        except Exception as e:
            print(f"[Search] loadFullResults failed: {e}")
        return '[]'

    @pyqtSlot(result=str)
    def getUiPrefs(self) -> str:
        """ui_prefs.json 전체를 JSON 문자열로 반환 — Vue가 mount 시 능동 복원용.

        uiPrefsLoaded 이벤트는 앱 startup에 1회만 emit되므로, 라우터+keep-alive로
        늦게 mount되는 SearchView가 그 이벤트를 놓칠 수 있음. 또 QWebEngine 저장소
        경로가 PID 기반이라 재시작 시 localStorage가 비워지는데, ui_prefs.json은
        파일이라 재시작 후에도 남음 → 이 getter로 능동 복원하면 검색 입력이 보존됨.
        """
        try:
            import os
            from core.config_migration import load_ui_prefs
            prefs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'ui_prefs.json')
            return json.dumps(load_ui_prefs(prefs_path), ensure_ascii=False)
        except Exception as e:
            print(f"[UIPrefs] getUiPrefs failed: {e}")
            return '{}'

    @pyqtSlot(str, result=str)
    def loadImageBase64(self, filepath: str) -> str:
        """이미지를 base64로 반환"""
        import base64, os
        clean = _normalize_vue_path(filepath)
        if not clean:
            return ''
        try:
            # base64는 원본보다 약 33% 커지므로 비정상적인 대용량 입력은 거절한다.
            if os.path.getsize(clean) > 64 * 1024 * 1024:
                logger.warning("loadImageBase64 blocked oversized image: %s", clean)
                return ''
        except OSError:
            return ''
        with open(clean, 'rb') as f:
            data = f.read()
        ext = os.path.splitext(clean)[1].lower()
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(ext, 'image/png')
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    def _load_upscalers_json(self) -> str:
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

    @pyqtSlot(result=str)
    def getUpscalers(self) -> str:
        """하위호환 동기 API. 신규 Vue 코드는 requestUpscalers를 사용한다."""
        return self._load_upscalers_json()

    @pyqtSlot()
    def requestUpscalers(self):
        """업스케일러 목록을 백그라운드에서 조회한다."""
        self._run_async_lookup('upscalers', self._load_upscalers_json, self.upscalersReady)

    @pyqtSlot(str, str, result=str)
    def saveImageExif(self, filepath: str, new_params: str) -> str:
        """이미지의 PNG 메타데이터(parameters)를 수정하여 저장"""
        tmp_path = ''
        try:
            import os, tempfile
            from PIL import Image as PILImage
            from PIL.PngImagePlugin import PngInfo
            clean = _normalize_vue_path(filepath)
            if not clean:
                return json.dumps({'error': '파일을 찾을 수 없습니다'})
            if not clean.lower().endswith('.png'):
                return json.dumps({'error': 'PNG 파일만 메타데이터 수정 가능'})
            with PILImage.open(clean) as img:
                meta = PngInfo()
                meta.add_text("parameters", new_params)
                # 기존 메타데이터 중 parameters 외 보존
                for k, v in img.info.items():
                    if k != "parameters" and isinstance(v, str):
                        meta.add_text(k, v)
                fd, tmp_path = tempfile.mkstemp(prefix='.exif_', suffix='.png', dir=os.path.dirname(clean))
                os.close(fd)
                img.save(tmp_path, pnginfo=meta)
            os.replace(tmp_path, clean)
            return json.dumps({'ok': True})
        except Exception as e:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, str, result=str)
    def renameFile(self, filepath: str, new_name: str) -> str:
        """파일 이름 변경"""
        try:
            import os
            from core.file_naming import sanitize_filename
            clean = _normalize_vue_path(filepath)
            if not clean:
                return json.dumps({'error': '파일을 찾을 수 없습니다'})
            dir_path = os.path.dirname(clean)
            ext = os.path.splitext(clean)[1]
            # 구분자 제거 — 새 이름은 같은 디렉토리 안의 단일 파일명만 허용
            stem, new_ext = os.path.splitext(new_name)
            new_name = sanitize_filename(stem, fallback='renamed', max_len=128) + (new_ext or '')
            if not new_name.endswith(ext):
                new_name += ext
            new_path = os.path.join(dir_path, new_name)
            if os.path.normcase(new_path) != os.path.normcase(clean) and os.path.exists(new_path):
                return json.dumps({'error': '같은 이름의 파일이 이미 존재합니다'})
            os.rename(clean, new_path)
            return json.dumps({'ok': True, 'new_path': new_path.replace('\\', '/')})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, int, int, result=str)
    def getEdgeMap(self, image_path: str, canny_low: int, canny_high: int) -> str:
        """Canny edge detection → base64 PNG (자석 올가미용)"""
        try:
            import cv2, base64
            from io import BytesIO
            from PIL import Image as PILImage
            clean = _normalize_vue_path(image_path)
            if not clean:
                return ''
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
        except Exception as e:
            logger.warning("getEdgeMap failed: %s", e)
            return ''

    @pyqtSlot(str, str, str)
    def ollamaEnhance(self, tags: str, mode: str, extra_json: str):
        """Ollama로 태그 강화 (비동기)"""
        try:
            # 이전 worker가 실행 중이면 정리
            if hasattr(self, '_ollama_worker') and self._ollama_worker and self._ollama_worker.isRunning():
                self._ollama_worker.disconnect()
                self._ollama_worker.quit()
                self._ollama_worker.wait(1000)
            extra = json.loads(extra_json) if extra_json else {}
            from workers.ollama_worker import OllamaWorker
            url = extra.get('url', 'http://localhost:11434')
            model = (extra.get('model') or '').strip()
            # 모델 검증 — 설치 목록과 대조해 없으면 첫 설치 모델로 대체.
            # (저장된 기본값 gemma3:4b 미설치, :latest 유무 등으로 모델 못 불러오던 문제 방지)
            try:
                from core.ollama_client import OllamaClient
                installed = OllamaClient(base_url=url).list_models()
                if installed:
                    def _b(s): return (s or '').split(':')[0].lower()
                    if not (model and any(m == model or _b(m) == _b(model) for m in installed)):
                        model = installed[0]
            except Exception:
                pass
            if not model:
                model = 'gemma3:4b'
            extra_prompt = extra.get('prompt', '')
            if mode == 'creative':
                # 창의 모드: 캐릭터의 실제 외견 태그를 DB에서 조회해 입력에 포함
                tags, extra_prompt = self._build_creative_input(tags, extra.get('character', ''))
            self._ollama_worker = OllamaWorker(url, model, tags, mode, extra_prompt, self)
            self._ollama_worker.finished.connect(lambda r: self.ollamaResult.emit(r))
            self._ollama_worker.error.connect(lambda e: self.ollamaResult.emit(json.dumps({'error': e})))
            self._ollama_worker.start()
        except Exception as e:
            self.ollamaResult.emit(json.dumps({'error': str(e)}))

    @pyqtSlot(str, str)
    def convertPromptToNl(self, text: str, extra_json: str):
        """생성 시 태그→자연어(nl_caption) 변환 — 전용 시그널 genNlResult로 결과 전달.
        PromptPanel의 ollamaResult 리스너와 충돌하지 않도록 별도 채널을 사용한다."""
        try:
            if hasattr(self, '_gennl_worker') and self._gennl_worker and self._gennl_worker.isRunning():
                self._gennl_worker.disconnect()
                self._gennl_worker.quit()
                self._gennl_worker.wait(1000)
            extra = json.loads(extra_json) if extra_json else {}
            from workers.ollama_worker import OllamaWorker
            url = extra.get('url', 'http://localhost:11434')
            model = (extra.get('model') or '').strip()
            # 모델 검증 (ollamaEnhance와 동일 — 미설치/별칭 문제 방지)
            try:
                from core.ollama_client import OllamaClient
                installed = OllamaClient(base_url=url).list_models()
                if installed:
                    def _b(s): return (s or '').split(':')[0].lower()
                    if not (model and any(m == model or _b(m) == _b(model) for m in installed)):
                        model = installed[0]
            except Exception:
                pass
            if not model:
                model = 'gemma3:4b'
            self._gennl_worker = OllamaWorker(url, model, text, 'nl_caption', '', self)
            self._gennl_worker.finished.connect(lambda r: self.genNlResult.emit(r))
            self._gennl_worker.error.connect(lambda e: self.genNlResult.emit(json.dumps({'error': e})))
            self._gennl_worker.start()
        except Exception as e:
            self.genNlResult.emit(json.dumps({'error': str(e)}))

    def _build_creative_input(self, hints: str, character: str):
        """창의 모드 입력 구성 — 캐릭터의 실제 외견 핵심 태그(우리 DB)를 함께 전달.
        태그 파일 전체를 LLM에 먹이는 대신, 해당 캐릭터의 검증된 외견 태그만 O(1) 조회해 주입."""
        character = (character or '').strip()
        hints = (hints or '').strip()
        feat = ''
        if character:
            first = character.split(',')[0].strip()
            # 1) 사용자가 저장한 프리셋(수정본) 우선 — danbooru로 고친 캐릭터 반영
            try:
                from utils.character_presets import get_character_preset_full
                preset = get_character_preset_full(first)
                if preset and (preset.get('extra_prompt') or '').strip():
                    feat = preset['extra_prompt'].strip()
            except Exception:
                pass
            # 2) 없으면 로컬 DB 핵심 특징
            if not feat:
                try:
                    from utils.character_features import get_character_features
                    core = get_character_features().lookup_core(first)
                    if core and core[0]:
                        feat = core[0]
                except Exception:
                    pass
        parts = []
        if character:
            parts.append(f"Character: {character}")
        if feat:
            parts.append(f"Canonical appearance tags (keep these accurate): {feat}")
        if hints:
            parts.append(f"Extra theme / hints (highest priority): {hints}")
        if not parts:
            parts.append("No specific character given — invent a fresh original anime character.")
        return "\n".join(parts), ''

    @pyqtSlot(str, str, result=str)
    def editorPasteImage(self, b64_data: str, mime_type: str) -> str:
        """클립보드 이미지를 임시 파일로 저장하고 경로 반환.

        Vue에서 navigator.clipboard.read()로 받은 base64 이미지 받음.
        """
        try:
            import base64
            import tempfile
            from pathlib import Path
            # mime_type 예: 'image/png', 'image/jpeg', ...
            ext = mime_type.split('/')[-1] if '/' in mime_type else 'png'
            if ext == 'jpeg':
                ext = 'jpg'
            raw = base64.b64decode(b64_data)
            # tempdir 경로 (앱 캐시 폴더 안에)
            tmp_dir = Path(tempfile.gettempdir()) / "AIStudioPro_editor"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            import time
            tmp_path = tmp_dir / f"clipboard_{int(time.time())}.{ext}"
            tmp_path.write_bytes(raw)
            return json.dumps({"path": str(tmp_path).replace('\\', '/')})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def editorAutoSave(self, path: str) -> str:
        """현재 편집 중인 파일을 임시 위치에 복사 → 크래시 복구용."""
        try:
            import shutil
            import time
            from pathlib import Path
            import tempfile
            clean = _normalize_vue_path(path)
            if not clean:
                return json.dumps({})
            src = Path(clean)
            tmp_dir = Path(tempfile.gettempdir()) / "AIStudioPro_editor"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            # 단일 복구 파일 (덮어쓰기)
            dst = tmp_dir / "_autosave_session.png"
            shutil.copy2(src, dst)
            # 원본 경로 메타 같이 저장
            meta = tmp_dir / "_autosave_session.meta.json"
            meta.write_text(
                json.dumps({"original": str(src), "saved_at": int(time.time())}),
                encoding="utf-8",
            )
            return json.dumps({"path": str(dst).replace('\\', '/')})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def editorCheckAutoSave(self) -> str:
        """앱 시작 시 호출 — 미저장 복구본 있는지 확인."""
        try:
            import time
            from pathlib import Path
            import tempfile
            tmp_dir = Path(tempfile.gettempdir()) / "AIStudioPro_editor"
            dst = tmp_dir / "_autosave_session.png"
            meta = tmp_dir / "_autosave_session.meta.json"
            if not dst.is_file():
                return json.dumps({"exists": False})
            saved_at = 0
            original = ""
            if meta.is_file():
                try:
                    m = json.loads(meta.read_text(encoding="utf-8"))
                    saved_at = int(m.get("saved_at", 0))
                    original = m.get("original", "")
                except Exception:
                    pass
            age_min = max(1, int((time.time() - saved_at) // 60)) if saved_at else 0
            # 24시간 초과면 무시 (오래된 복구본은 자동 정리 권장)
            if saved_at and (time.time() - saved_at) > 86400:
                try:
                    dst.unlink()
                    if meta.exists():
                        meta.unlink()
                except OSError:
                    pass
                return json.dumps({"exists": False})
            return json.dumps({
                "exists": True,
                "path": str(dst).replace('\\', '/'),
                "basename": Path(original).name if original else dst.name,
                "age_minutes": age_min,
            })
        except Exception:
            return json.dumps({"exists": False})

    @pyqtSlot(result=str)
    def editorClearAutoSave(self) -> str:
        """복구본 폐기."""
        try:
            from pathlib import Path
            import tempfile
            tmp_dir = Path(tempfile.gettempdir()) / "AIStudioPro_editor"
            for fn in ("_autosave_session.png", "_autosave_session.meta.json"):
                p = tmp_dir / fn
                if p.exists():
                    p.unlink()
            return json.dumps({"cleared": True})
        except Exception:
            return json.dumps({"cleared": False})

    @pyqtSlot(str, result=str)
    def getFileInfo(self, path: str) -> str:
        """파일 기본 정보 반환 (포맷/용량)."""
        try:
            from pathlib import Path
            clean = _normalize_vue_path(path)
            if not clean:
                return json.dumps({})
            p = Path(clean)
            stat = p.stat()
            ext = p.suffix.lstrip('.').upper() or ''
            return json.dumps({"size": stat.st_size, "format": ext})
        except Exception:
            return json.dumps({})

    def _load_ollama_models_json(self, base_url: str = '') -> str:
        try:
            from core.ollama_client import OllamaClient
            url = base_url.strip() if base_url.strip() else 'http://localhost:11434'
            client = OllamaClient(base_url=url)
            models = client.list_models()
            return json.dumps(models)
        except Exception as e:
            print(f"[Ollama] ollamaListModels 오류: {e}")
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def ollamaListModels(self, base_url: str = '') -> str:
        """하위호환 동기 API. 신규 Vue 코드는 requestOllamaModels를 사용한다."""
        return self._load_ollama_models_json(base_url)

    @pyqtSlot(str)
    def requestOllamaModels(self, base_url: str = ''):
        """Ollama 모델 목록을 백그라운드에서 조회한다."""
        url = base_url.strip() if base_url.strip() else 'http://localhost:11434'

        def _load():
            return json.dumps({
                'url': url,
                'models': json.loads(self._load_ollama_models_json(url)),
            })

        self._run_async_lookup(f'ollama-models:{url}', _load, self.ollamaModelsReady)

    @pyqtSlot(result=str)
    def getRandomResolutions(self) -> str:
        """랜덤 해상도 목록 반환"""
        try:
            gen = self.parent()
            if gen and hasattr(gen, 'random_resolutions'):
                return json.dumps(gen.random_resolutions)
        except Exception:
            pass
        return json.dumps([])

    @pyqtSlot(result=str)
    def getInitialConfig(self) -> str:
        """클라이언트별 초기 설정 응답.

        QWebChannel 시그널 재발행은 연결된 모든 브라우저에 방송되므로, 새 웹
        클라이언트 하나가 기존 클라이언트 상태까지 다시 덮어쓰지 않게 직접 반환한다.
        """
        root = os.path.dirname(os.path.dirname(__file__))

        def _load(name, default):
            try:
                path = os.path.join(root, 'config', name)
                if os.path.isfile(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                logger.warning("initial config load failed (%s): %s", name, e)
            return default

        try:
            ui_prefs = json.loads(self.getUiPrefs() or '{}')
        except Exception:
            ui_prefs = {}
        try:
            tab_defaults = json.loads(self.getTabDefaults() or '{}')
        except Exception:
            tab_defaults = {}
        return json.dumps({
            'uiPrefs': ui_prefs,
            'condRules': _load('cond_rules.json', {'positive': [], 'negative': []}),
            'globalWeights': _load('global_weights.json', []),
            'tabDefaults': tab_defaults,
        }, ensure_ascii=False)

    @pyqtSlot(result=str)
    def requestInitialConfig(self) -> str:
        """구버전 프론트 호환 별칭 — 더 이상 전역 시그널을 재발행하지 않는다."""
        return self.getInitialConfig()

    @pyqtSlot(result=str)
    def getGenStats(self) -> str:
        """생성 통계 요약 반환"""
        try:
            from core.gen_stats import get_gen_stats
            return json.dumps(get_gen_stats().get_summary())
        except Exception:
            return json.dumps({'total': 0})

    @pyqtSlot(result=str)
    def getWildcardTree(self) -> str:
        """wildcards/ 디렉토리의 파일 트리 + 내용 반환"""
        import os
        wc_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wildcards')
        if not os.path.isdir(wc_dir):
            return json.dumps([])
        tree = []
        for f in sorted(os.listdir(wc_dir)):
            fp = os.path.join(wc_dir, f)
            if not f.endswith('.txt') or not os.path.isfile(fp):
                continue
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    lines = [l.strip() for l in fh if l.strip() and not l.startswith('#')]
                tree.append({'name': f.replace('.txt', ''), 'file': f, 'tags': lines})
            except Exception:
                pass
        return json.dumps(tree)

    vramUpdated = pyqtSignal(str)  # JSON {used, total, pct}

    @pyqtSlot(result=str)
    def getPresetList(self) -> str:
        """프리셋 목록 반환"""
        import os
        preset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets')
        os.makedirs(preset_dir, exist_ok=True)
        files = [f.replace('.json', '') for f in sorted(os.listdir(preset_dir)) if f.endswith('.json')]
        return json.dumps(files)

    @pyqtSlot(str, result=str)
    def getPresetData(self, name: str) -> str:
        """프리셋 데이터 반환"""
        import os
        from core.file_naming import sanitize_filename
        preset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'presets')
        # 읽기 경로도 정규화 — 저장/삭제와 동일 규칙(traversal 차단, 라운드트립 일치)
        fp = os.path.join(preset_dir, f"{sanitize_filename(name, fallback='')}.json")
        try:
            if os.path.exists(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            logger.warning("getPreset failed (%s): %s", name, e)
        return '{}'

    # ══════════ 캐릭터 특징 프리셋 (Vue 모달) ══════════

    def _current_prompt_norm_tags(self) -> set:
        """현재 프롬프트(main/prefix/suffix/character)의 정규화 태그 집합 (중복 표시용)."""
        gen = self.parent()
        out: set = set()
        if not gen:
            return out
        for attr in ('main_prompt_text', 'prefix_prompt_text',
                     'suffix_prompt_text', 'character_input'):
            w = getattr(gen, attr, None)
            if w is None:
                continue
            if hasattr(w, 'toPlainText'):
                src = w.toPlainText()
            elif hasattr(w, 'text'):
                src = w.text()
            else:
                continue
            for t in src.split(","):
                n = t.strip().lower().replace("_", " ")
                if n:
                    out.add(n)
                    out.add(n.replace(r"\(", "(").replace(r"\)", ")"))
        return out

    @pyqtSlot(str, result=str)
    def searchCharacters(self, query: str) -> str:
        """캐릭터 이름 검색 → JSON [{key, count, hasPreset}] (2글자 미만은 빈 배열)."""
        try:
            q = (query or "").strip()
            if len(q) < 2:
                return json.dumps([])
            from utils.character_features import get_character_features
            from utils.character_presets import list_character_presets
            lookup = get_character_features()
            results = lookup.search(q, limit=80)
            saved = list_character_presets()
            out = []
            for orig_key, _features, count in results:
                norm = orig_key.strip().lower().replace("_", " ")
                out.append({
                    "key": orig_key,
                    "count": int(count or 0),
                    "hasPreset": norm in saved,
                })
            return json.dumps(out, ensure_ascii=False)
        except Exception as e:
            print(f"[CharPreset] searchCharacters 실패: {e}")
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def getCharacterFeatures(self, name: str) -> str:
        """캐릭터 → 핵심/의상 특징 분리 + 저장된 커스텀/조건부 규칙.
        Returns JSON {name, count, core:[{tag,existing,costume}], costume:[...],
                      custom:[str], hasPreset, condRulesJson}
        """
        try:
            from utils.character_features import get_character_features
            from utils.character_presets import get_character_preset_full
            lookup = get_character_features()
            core = lookup.lookup_core(name)
            aux = lookup.lookup_aux(name)
            costume = lookup.lookup_costume(name)
            etc = lookup.lookup_etc(name)
            full = lookup.lookup(name)
            count = (core[1] if core else 0) or (full[1] if full else 0)

            existing = self._current_prompt_norm_tags()
            char_norm = name.strip().lower().replace("_", " ")

            from core.tag_intelligence import get_tag_intelligence
            ti = get_tag_intelligence()

            def _split(s):
                return [t.strip() for t in s.split(",") if t.strip()] if s else []

            core_tags = _split(core[0]) if core else []
            aux_tags = _split(aux[0]) if aux else []
            costume_tags = _split(costume[0]) if costume else []
            etc_tags = _split(etc[0]) if etc else []
            if not core_tags and not aux_tags and not costume_tags and not etc_tags and full:
                core_tags = _split(full[0])

            def _mk(tags, is_costume):
                items = []
                for t in tags:
                    norm = t.strip().lower().replace("_", " ")
                    if norm == char_norm:
                        continue
                    esc = norm.replace("(", r"\(").replace(")", r"\)")
                    item = {
                        "tag": t,
                        "existing": (norm in existing or esc in existing),
                        "costume": is_costume,
                    }
                    if is_costume:   # ④ 의상 부위(region) 태깅
                        r = ti.region_of(t)
                        item["region"] = r or "UNASSIGNED"
                        item["regionLabel"] = ti.region_label(r or "UNASSIGNED")
                    items.append(item)
                return items

            custom = []
            cond_json = ""
            has_preset = False
            preset = get_character_preset_full(name)
            if preset:
                has_preset = True
                cond_json = preset.get("cond_rules_json", "") or ""
                feature_norms = {
                    t.strip().lower().replace("_", " ")
                    for t in (core_tags + aux_tags + costume_tags + etc_tags)
                }
                for t in (preset.get("extra_prompt", "") or "").split(","):
                    tag = t.strip()
                    n = tag.lower().replace("_", " ")
                    if n and n not in feature_norms:
                        custom.append(tag)

            # ③ copyright(시리즈) + 자동추가 설정
            copyright_tag = ""
            auto_copy = True
            try:
                copyright_tag = ti.copyright_of(name) or ""
            except Exception:
                pass
            gen = self.parent()
            if gen is not None and hasattr(gen, "_get_ui_pref"):
                auto_copy = bool(gen._get_ui_pref("autoAddCopyright", True))

            return json.dumps({
                "name": name,
                "count": int(count or 0),
                "core": _mk(core_tags, False),
                "aux": _mk(aux_tags, False),
                "etc": _mk(etc_tags, False),
                "costume": _mk(costume_tags, True),
                "custom": custom,
                "hasPreset": has_preset,
                "condRulesJson": cond_json,
                "copyright": copyright_tag,
                "autoAddCopyright": auto_copy,
            }, ensure_ascii=False)
        except Exception as e:
            print(f"[CharPreset] getCharacterFeatures 실패: {e}")
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def getCharacterCopyright(self, name: str) -> str:
        """캐릭터 → copyright(시리즈) 태그. {copyright: str}."""
        try:
            from core.tag_intelligence import get_tag_intelligence
            return json.dumps(
                {"copyright": get_tag_intelligence().copyright_of(name) or ""},
                ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def fetchCharacterTagsOnline(self, name: str) -> str:
        """danbooru에서 캐릭터의 실제 공통 general 태그를 라이브 집계 (로컬 DB가 틀린/없는 캐릭터 보완).
        posts.json 표본의 tag_string_general 빈도 집계 → 상위 태그."""
        try:
            import requests
            from collections import Counter
            tag = (name or '').strip().lower().replace(' ', '_')
            if not tag:
                return json.dumps({"error": "캐릭터 이름 없음"})
            hdr = {"User-Agent": "UR_IV/1.0 (character tag lookup)"}
            posts = []
            for q in (f"{tag} solo", tag):
                try:
                    r = requests.get(
                        "https://danbooru.donmai.us/posts.json",
                        params={"tags": q, "limit": 100, "only": "tag_string_general"},
                        timeout=12, headers=hdr,
                    )
                    r.raise_for_status()
                    posts = r.json()
                    if isinstance(posts, list) and posts:
                        break
                except Exception:
                    continue
            if not isinstance(posts, list) or not posts:
                return json.dumps({"error": "danbooru 게시물 없음 (이름/철자 확인)"})
            cnt = Counter()
            n = 0
            for p in posts:
                g = p.get("tag_string_general") if isinstance(p, dict) else ""
                if not g:
                    continue
                n += 1
                for t in g.split():
                    cnt[t] += 1
            if not n:
                return json.dumps({"error": "태그 없음"})
            ranked = [t.replace("_", " ") for t, _c in cnt.most_common(60)]
            return json.dumps({"tags": ranked[:40], "sampled": n}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, str, result=str)
    def separateTags(self, prompt: str, categories_json: str) -> str:
        """⑤ 프롬프트를 카테고리별로 분리. categories=대상 카테고리 리스트.
        Returns {rest:'...', groups:{cat:[...]}, counts:{cat:n}}.
        (rest = 어떤 대상 카테고리에도 속하지 않은 태그 = 카테고리 제거 결과)"""
        try:
            from core.tag_intelligence import get_tag_intelligence
            cats = json.loads(categories_json) if categories_json else []
            tags = [t.strip() for t in (prompt or "").split(",") if t.strip()]
            res = get_tag_intelligence().split_by_categories(tags, cats)
            counts = {c: len(v) for c, v in res["groups"].items()}
            return json.dumps({
                "rest": ", ".join(res["rest"]),
                "groups": res["groups"],
                "counts": counts,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def pairColors(self, prompt: str) -> str:
        """② 분리된 단일 색상 단어를 바로 뒤 태그와 결합 (결합 결과가 실재 태그일 때만).
        Returns {result:'...', before:n, after:m, merged:k}."""
        try:
            from core.tag_intelligence import get_tag_intelligence
            tags = [t.strip() for t in (prompt or "").split(",") if t.strip()]
            paired = get_tag_intelligence().pair_colors(tags)
            return json.dumps({
                "result": ", ".join(paired),
                "before": len(tags),
                "after": len(paired),
                "merged": len(tags) - len(paired),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def refineToSpecificTags(self, prompt: str) -> str:
        """덜 구체적인(상위) 태그 제거 — muscular+muscular male → muscular male,
        dress+blue dress → blue dress. Returns {result, before, after, removed:[...]}"""
        try:
            from core.tag_intelligence import get_tag_intelligence
            tags = [t.strip() for t in (prompt or "").split(",") if t.strip()]
            kept, removed = get_tag_intelligence().remove_redundant_subtags(tags)
            return json.dumps({
                "result": ", ".join(kept),
                "before": len(tags),
                "after": len(kept),
                "removed": removed,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def getLoras(self, mode: str = '') -> str:
        """설치된 LoRA 목록 → [{name, triggerWords}]. mode='force'면 캐시 무시하고 재스캔.
        (시작 시 프리로드된 LoraManagerDialog._lora_cache 사용 → 즉시 반환)"""
        try:
            from widgets.lora_manager import LoraManagerDialog
            loras = LoraManagerDialog._lora_cache
            if mode == 'force' or not loras:
                from backends import get_backend
                b = get_backend()
                fresh = b.get_loras() if b else []
                if fresh:
                    loras = fresh
                    LoraManagerDialog._lora_cache = fresh
            out = []
            for l in (loras or []):
                if isinstance(l, dict):
                    name = l.get('name') or l.get('alias') or ''
                    tws = l.get('trigger_words') or l.get('triggerWords') or []
                else:
                    name, tws = str(l), []
                if name:
                    out.append({"name": name, "triggerWords": list(tws)[:12]})
            return json.dumps(out, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def saveSession(self, payload_json: str) -> str:
        """세션 상태(탭/프롬프트 등)를 config/session_backup.json에 저장 (크래시 복구용).
        localStorage가 PID별로 초기화돼도 살아남도록 백엔드 파일에 보관."""
        try:
            import os
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, 'config', 'session_backup.json')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(payload_json or '{}')
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def getSession(self) -> str:
        """저장된 세션 상태 반환 (없으면 {})."""
        try:
            import os
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, 'config', 'session_backup.json')
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    return f.read() or '{}'
            return json.dumps({})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def getClothingRegions(self, tags_json: str) -> str:
        """④ 의류 태그를 부위(region)별로 그룹화 → [{region, label, tags:[...]}]."""
        try:
            from core.tag_intelligence import get_tag_intelligence
            tags = json.loads(tags_json) if tags_json else []
            groups = get_tag_intelligence().group_by_region(tags)
            return json.dumps({"groups": groups}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, str, str, result=str)
    def saveCharacterPreset(self, name: str, tags_json: str, cond_rules_json: str) -> str:
        """캐릭터 프리셋 저장 (선택된 태그 + 조건부 규칙 JSON)."""
        try:
            from utils.character_presets import save_character_preset
            tags = json.loads(tags_json) if tags_json else []
            combined = ", ".join(str(t).strip() for t in tags if str(t).strip())
            save_character_preset(name, combined, cond_rules_json or "")
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def deleteCharacterPreset(self, name: str) -> str:
        """캐릭터 프리셋 삭제."""
        try:
            from utils.character_presets import delete_character_preset, has_preset
            if not has_preset(name):
                return json.dumps({"ok": False, "reason": "프리셋 없음"})
            delete_character_preset(name)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def getCharGlobalPrefs(self) -> str:
        """캐릭터 프리셋 글로벌 설정 로드 (모든 캐릭터 공통).
        {categoryOff: [핵심/보조/의상/기타 중 OFF인 것], wordOff: [전역 제외 단어]}"""
        try:
            import os
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                'config', 'char_global_prefs.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                return json.dumps({
                    "categoryOff": list(d.get("categoryOff", [])),
                    "wordOff": list(d.get("wordOff", [])),
                })
        except Exception:
            pass
        # 기본값: 기타 카테고리만 OFF
        return json.dumps({"categoryOff": ["etc"], "wordOff": []})

    @pyqtSlot(str, result=str)
    def saveCharGlobalPrefs(self, prefs_json: str) -> str:
        """캐릭터 프리셋 글로벌 설정 저장."""
        try:
            import os
            d = json.loads(prefs_json) if prefs_json else {}
            base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')
            os.makedirs(base, exist_ok=True)
            with open(os.path.join(base, 'char_global_prefs.json'), 'w', encoding='utf-8') as f:
                json.dump({
                    "categoryOff": list(d.get("categoryOff", [])),
                    "wordOff": list(d.get("wordOff", [])),
                }, f, ensure_ascii=False, indent=2)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def applyCharacterPreset(self, payload_json: str) -> str:
        """Vue 모달의 적용 결과를 프롬프트 위젯에 반영.
        payload: {character: str|'', tags: [str]}
        """
        try:
            gen = self.parent()
            if not gen or not hasattr(gen, '_apply_character_features_result'):
                return json.dumps({"error": "메인 윈도우 없음"})
            payload = json.loads(payload_json) if payload_json else {}
            gen._apply_character_features_result(
                (payload.get("character") or "").strip(),
                payload.get("tags", []) or [],
                add_copyright=payload.get("addCopyright"),
            )
            return json.dumps({"ok": True})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def getDeckCharacters(self) -> str:
        """현재 자동화 덱(또는 filtered_results)에 등장하는 캐릭터 정규화 집합 → JSON [str]."""
        try:
            gen = self.parent()
            deck = (getattr(gen, 'shuffled_prompt_deck', None)
                    or getattr(gen, 'filtered_results', None) or [])
            chars: set = set()
            for b in deck:
                if not isinstance(b, dict):
                    continue
                cval = b.get('character', '') or ''
                if not cval:
                    continue
                parts = cval.split(',') if ',' in cval else cval.split()
                for p in parts:
                    n = p.strip().lower().replace('_', ' ')
                    if n:
                        chars.add(n)
            return json.dumps(sorted(chars), ensure_ascii=False)
        except Exception as e:
            print(f"[CharPreset] getDeckCharacters 실패: {e}")
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def submitABTest(self, payload_json: str) -> str:
        """A/B 테스트: prompt_a, prompt_b 를 같은 시드로 큐에 추가.
        payload: {prompt_a, prompt_b, negative, seed}
        """
        try:
            gen = self.parent()
            p = json.loads(payload_json) if payload_json else {}
            try:
                seed = int(p.get("seed", -1))
            except (ValueError, TypeError):
                seed = -1
            if seed <= 0:
                import random
                seed = random.randint(1, 2147483647)
            neg = p.get("negative", "") or ""
            added = 0
            for key in ("prompt_a", "prompt_b"):
                prm = (p.get(key) or "").strip()
                if not prm:
                    continue
                item = {"prompt": prm, "negative_prompt": neg, "seed": seed}
                if gen and hasattr(gen, "queue_panel"):
                    gen.queue_panel.add_single_item(item)
                    added += 1
            return json.dumps({"ok": True, "seed": seed, "added": added})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def getCharFeatureOverride(self) -> str:
        """auto-remove override 설정 조회 → JSON {hair_length, eye_color}."""
        gen = self.parent()
        ov = getattr(gen, '_char_feature_override', None) or {}
        return json.dumps({
            "hair_length": bool(ov.get("hair_length")),
            "eye_color": bool(ov.get("eye_color")),
        })

    @pyqtSlot(str, result=str)
    def setCharFeatureOverride(self, payload_json: str) -> str:
        """auto-remove override 설정 저장."""
        try:
            gen = self.parent()
            p = json.loads(payload_json) if payload_json else {}
            if gen is not None:
                gen._char_feature_override = {
                    "hair_length": bool(p.get("hair_length")),
                    "eye_color": bool(p.get("eye_color")),
                }
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @staticmethod
    def _wildcard_path(name: str) -> str:
        """와일드카드 이름 → wildcards/ 안의 안전한 .txt 경로 (탈출 차단)."""
        import os
        from core.file_naming import sanitize_filename
        wc_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'wildcards')
        os.makedirs(wc_dir, exist_ok=True)
        if name.endswith('.txt'):
            name = name[:-4]
        return os.path.join(wc_dir, sanitize_filename(name, fallback='wildcard') + '.txt')

    @pyqtSlot(str, str, result=str)
    def saveWildcard(self, filename: str, content: str) -> str:
        """와일드카드 파일 저장/수정"""
        try:
            with open(self._wildcard_path(filename), 'w', encoding='utf-8') as f:
                f.write(content)
            return json.dumps({'ok': True})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, result=str)
    def deleteWildcard(self, filename: str) -> str:
        """와일드카드 파일 삭제"""
        import os
        try:
            fp = self._wildcard_path(filename)
            if os.path.exists(fp): os.remove(fp)
            return json.dumps({'ok': True})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, str, result=str)
    def renameWildcard(self, old_name: str, new_name: str) -> str:
        """와일드카드 파일 이름 변경"""
        import os
        try:
            old_fp = self._wildcard_path(old_name)
            new_fp = self._wildcard_path(new_name)
            if os.path.exists(old_fp): os.rename(old_fp, new_fp)
            return json.dumps({'ok': True})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, result=str)
    def getExcludeMatches(self, rule: str) -> str:
        """제외 규칙에 매칭되는 태그 목록 반환 (tags_db 기반)"""
        try:
            rule = rule.strip()
            if not rule or rule.startswith('~'):
                return json.dumps([])

            # tags_db에서 모든 태그 수집
            if not hasattr(self, '_all_tags_set'):
                self._all_tags_set = set()
                import os
                tags_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tags_db')
                # clothes_list.txt
                for txt_file in ['clothes_list.txt', 'characteristic_list.txt']:
                    fp = os.path.join(tags_db, txt_file)
                    if os.path.exists(fp):
                        with open(fp, 'r', encoding='utf-8') as f:
                            for line in f:
                                t = line.strip().lower()
                                if t: self._all_tags_set.add(t)
                # parquet 파일들
                try:
                    import pandas as pd
                    for fn in os.listdir(tags_db):
                        if fn.endswith('.parquet'):
                            try:
                                df = pd.read_parquet(os.path.join(tags_db, fn))
                                col = df.columns[0] if len(df.columns) > 0 else None
                                if col:
                                    for v in df[col].dropna():
                                        self._all_tags_set.add(str(v).strip().lower())
                            except Exception as e:
                                logger.debug("parquet read failed (%s): %s", fn, e)
                except Exception as e:
                    logger.warning("tags_db scan failed: %s", e)
                # TagClassifier의 tag_to_category
                try:
                    from core.tag_classifier import TagClassifier
                    if not hasattr(self, '_tag_classifier'):
                        self._tag_classifier = TagClassifier()
                    self._all_tags_set.update(self._tag_classifier.tag_to_category.keys())
                except Exception as e:
                    logger.debug("TagClassifier categories load failed: %s", e)
                # character/copyright/artist 사전도 추가
                try:
                    from core.tag_classifier import TagClassifier
                    if not hasattr(self, '_tag_classifier'):
                        self._tag_classifier = TagClassifier()
                    tc = self._tag_classifier
                    if hasattr(tc, 'characters'): self._all_tags_set.update(t.lower() for t in tc.characters)
                    if hasattr(tc, 'copyrights'): self._all_tags_set.update(t.lower() for t in tc.copyrights)
                    if hasattr(tc, 'artists'): self._all_tags_set.update(t.lower() for t in tc.artists)
                except Exception as e:
                    logger.debug("TagClassifier name dicts load failed: %s", e)
                print(f"[Exclude] Tag DB loaded: {len(self._all_tags_set)} tags")

            # 규칙 매칭
            rule_lower = rule.lower().replace(' ', '_')
            matches = []
            if rule_lower.startswith('~'):
                matches = []
            elif rule_lower.startswith('*'):
                keyword = rule_lower[1:]
                matches = [t for t in self._all_tags_set if t == keyword]
            elif rule_lower.startswith('_') and rule_lower.endswith('_') and len(rule_lower) > 2:
                keyword = rule_lower[1:-1]
                matches = [t for t in self._all_tags_set if keyword in t]
            elif rule_lower.startswith('_'):
                keyword = rule_lower[1:]
                matches = [t for t in self._all_tags_set if t.endswith(keyword)]
            elif rule_lower.endswith('_'):
                keyword = rule_lower[:-1]
                matches = [t for t in self._all_tags_set if t.startswith(keyword)]
            else:
                matches = [t for t in self._all_tags_set if rule_lower in t]

            matches.sort()
            return json.dumps(matches)
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, result=str)
    def deepCleanPrompt(self, prompt_json: str) -> str:
        """딥 프롬프트 클리너: 충돌 감지 + 중복 제거 + 최적 순서 재배치"""
        try:
            data = json.loads(prompt_json) if isinstance(prompt_json, str) else prompt_json
            tags = [t.strip() for t in data.get('prompt', '').split(',') if t.strip()]

            # 1. 중복 제거
            seen = set()
            unique = []
            for t in tags:
                tl = t.lower().replace(' ', '_')
                if tl not in seen:
                    seen.add(tl)
                    unique.append(t)

            # 2. 충돌 감지
            conflicts = []
            conflict_pairs = [
                (['black_hair', 'blonde_hair', 'brown_hair', 'red_hair', 'blue_hair', 'green_hair', 'white_hair', 'pink_hair', 'purple_hair', 'silver_hair', 'orange_hair', 'grey_hair'], '머리색'),
                (['blue_eyes', 'red_eyes', 'green_eyes', 'brown_eyes', 'yellow_eyes', 'purple_eyes', 'pink_eyes', 'grey_eyes', 'black_eyes', 'orange_eyes'], '눈색'),
                (['short_hair', 'long_hair', 'very_long_hair', 'medium_hair'], '머리 길이'),
                (['standing', 'sitting', 'lying', 'kneeling', 'squatting'], '포즈'),
                (['day', 'night', 'sunset', 'sunrise'], '시간'),
                (['indoors', 'outdoors'], '장소'),
            ]
            tag_lower = {t.lower().replace(' ', '_') for t in unique}
            for group, label in conflict_pairs:
                found = [t for t in group if t in tag_lower]
                if len(found) > 1:
                    conflicts.append({'group': label, 'tags': found})

            # 3. 최적 순서 재배치 (작가→캐릭터→품질→배경→포즈→의상→기타)
            quality_tags = {'masterpiece', 'best_quality', 'high_quality', 'absurdres', 'highres'}
            count_pattern = ['1girl', '2girls', '3girls', '1boy', '2boys', 'solo', 'multiple_girls', 'multiple_boys']

            ordered = {'count': [], 'quality': [], 'body': [], 'clothing': [], 'pose': [], 'bg': [], 'other': []}
            for t in unique:
                tl = t.lower().replace(' ', '_')
                if tl in quality_tags: ordered['quality'].append(t)
                elif any(tl == c for c in count_pattern): ordered['count'].append(t)
                else: ordered['other'].append(t)

            optimized = ordered['count'] + ordered['quality'] + ordered['body'] + ordered['clothing'] + ordered['pose'] + ordered['bg'] + ordered['other']

            removed_count = len(tags) - len(unique)
            return json.dumps({
                'optimized': ', '.join(optimized),
                'removed': removed_count,
                'conflicts': conflicts,
                'tag_count': len(optimized),
            })
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, result=str)
    def getCharacterInsight(self, character: str) -> str:
        """캐릭터 공식 설정(description) 반환 (JSONL 기반)"""
        try:
            import os
            jsonl_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'danbooru_character_description_full.jsonl')
            if not os.path.exists(jsonl_path):
                return json.dumps({'error': 'JSONL not found'})
            # 캐시
            if not hasattr(self, '_char_desc_cache'):
                self._char_desc_cache = {}
                with open(jsonl_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            d = json.loads(line)
                            name = d.get('character', '').lower().strip()
                            desc = d.get('description', '')
                            if name and desc:
                                self._char_desc_cache[name] = desc
                        except: continue
                print(f"[CharInsight] Loaded {len(self._char_desc_cache)} characters")
            # 검색
            char_lower = character.lower().strip().replace(' ', '_')
            desc = self._char_desc_cache.get(char_lower, '')
            if not desc:
                for k, v in self._char_desc_cache.items():
                    if char_lower in k:
                        desc = v; break
            if desc:
                tags = [t.strip() for t in desc.split(',') if t.strip()]
                return json.dumps({'character': character, 'tags': tags, 'raw': desc})
            return json.dumps({'tags': [], 'raw': ''})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, result=str)
    def classifyTags(self, tags_json: str) -> str:
        """태그 목록을 분류하여 카테고리별로 반환 (tags_db 기반)"""
        try:
            tags = json.loads(tags_json) if isinstance(tags_json, str) else tags_json
            result = {}

            # TagClassifier 시도
            tc = None
            try:
                from core.tag_classifier import TagClassifier
                if not hasattr(self, '_tag_classifier'):
                    self._tag_classifier = TagClassifier()
                tc = self._tag_classifier
            except Exception:
                pass

            # fallback: clothes_list.txt 기반 간이 분류
            if not hasattr(self, '_fallback_clothes'):
                self._fallback_clothes = set()
                self._fallback_sexual = set()
                import os
                tags_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tags_db')
                # clothes_list.txt
                cl_path = os.path.join(tags_db, 'clothes_list.txt')
                if os.path.exists(cl_path):
                    with open(cl_path, 'r', encoding='utf-8') as f:
                        self._fallback_clothes = {line.strip().lower() for line in f if line.strip()}
                # sexual keywords from known parquet names
                for fn in ['sex_acts.parquet', 'nudity.parquet', 'pussy.parquet', 'sexual_positions.parquet', 'sexual_attire.parquet', 'sex_objects.parquet']:
                    fp = os.path.join(tags_db, fn)
                    if os.path.exists(fp):
                        try:
                            import pandas as pd
                            df = pd.read_parquet(fp)
                            col = df.columns[0] if len(df.columns) > 0 else None
                            if col:
                                self._fallback_sexual.update(df[col].str.lower().tolist())
                        except Exception:
                            pass

            for tag in tags:
                t = tag.strip().lower().replace(' ', '_')
                if tc:
                    cat = tc.classify_tag(t)
                    result[tag] = cat
                else:
                    # fallback 분류
                    if t in self._fallback_sexual:
                        result[tag] = 'sexual'
                    elif t in self._fallback_clothes:
                        result[tag] = 'clothing'
                    elif any(kw in t for kw in ['breast', 'thigh', 'ass', 'navel', 'nipple', 'penis', 'pussy', 'anus']):
                        result[tag] = 'body_parts'
                    elif any(kw in t for kw in ['stand', 'sit', 'ly', 'kneel', 'squat', 'walk', 'run', 'jump', 'smile', 'blush', 'cry', 'open_mouth']):
                        result[tag] = 'pose'
                    elif any(kw in t for kw in ['outdoor', 'indoor', 'sky', 'night', 'beach', 'forest', 'city', 'school', 'water', 'snow']):
                        result[tag] = 'background'
                    elif any(kw in t for kw in ['sex', 'vaginal', 'anal', 'oral', 'cum', 'nude', 'naked', 'penetrat']):
                        result[tag] = 'sexual'
                    else:
                        result[tag] = 'general'
            return json.dumps(result)
        except Exception as e:
            from core.error_handler import handle_error
            handle_error('E050', 'ClassifyTags', e, notify=False)
            return json.dumps({'error': str(e)})

    @pyqtSlot(str, str, int, int, result=str)
    def exportCompareGif(self, before_path: str, after_path: str, duration: int, loops: int) -> str:
        """Before/After 비교 GIF 생성"""
        try:
            from PIL import Image as PILImage
            import os, time

            clean_before = _normalize_vue_path(before_path)
            clean_after = _normalize_vue_path(after_path)
            if not clean_before or not clean_after:
                return json.dumps({'error': '비교 이미지 경로가 올바르지 않습니다'})
            img_a = PILImage.open(clean_before)
            img_b = PILImage.open(clean_after)

            # 크기 통일 (작은 쪽에 맞춤)
            w = min(img_a.width, img_b.width)
            h = min(img_a.height, img_b.height)
            img_a = img_a.resize((w, h), PILImage.LANCZOS)
            img_b = img_b.resize((w, h), PILImage.LANCZOS)

            # 중간 프레임 생성 (부드러운 전환)
            frames = []
            steps = 8
            for i in range(steps + 1):
                alpha = i / steps
                blended = PILImage.blend(img_a, img_b, alpha)
                frames.append(blended)
            # 역방향
            for i in range(steps - 1, 0, -1):
                alpha = i / steps
                blended = PILImage.blend(img_a, img_b, alpha)
                frames.append(blended)

            out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gif')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"compare_{int(time.time())}.gif")

            frames[0].save(
                out_path, save_all=True, append_images=frames[1:],
                duration=duration, loop=loops, optimize=True
            )
            return json.dumps({'path': out_path.replace('\\', '/'), 'frames': len(frames)})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @pyqtSlot(result=str)
    def getTabDefaults(self) -> str:
        """tab_defaults.json 반환"""
        import os
        fp = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'tab_defaults.json')
        try:
            if os.path.exists(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            logger.warning("getTabDefaults failed: %s", e)
        return '{}'

    def _load_adetailer_models_json(self) -> str:
        models = ["face_yolov8n.pt", "hand_yolov8n.pt", "person_yolov8n-seg.pt",
                   "mediapipe_face_full", "mediapipe_face_short"]
        try:
            from backends import get_backend
            backend = get_backend()
            if backend:
                import requests
                r = requests.get(f"{backend.api_url}/adetailer/v1/ad_model", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    models = data if isinstance(data, list) else data.get('ad_model', [])
        except Exception:
            pass
        return json.dumps(models)

    @pyqtSlot(str)
    def _apply_adetailer_models_json(self, models_json: str):
        """worker 결과를 GUI 스레드에서 proxy 목록에 반영한다."""
        try:
            models = json.loads(models_json)
        except Exception:
            return
        for wid in ('_ad_s1_model', '_ad_s2_model'):
            proxy = self._proxies.get(wid)
            if proxy and hasattr(proxy, 'addItems'):
                proxy.addItems(models)

    @pyqtSlot(result=str)
    def getADetailerModels(self) -> str:
        """하위호환 동기 API. 신규 Vue 코드는 requestADetailerModels를 사용한다."""
        models_json = self._load_adetailer_models_json()
        self._apply_adetailer_models_json(models_json)
        return models_json

    @pyqtSlot()
    def requestADetailerModels(self):
        """ADetailer 모델 목록을 백그라운드에서 조회한다."""
        self._run_async_lookup(
            'adetailer-models',
            self._load_adetailer_models_json,
            self.adetailerModelsReady,
        )

    @pyqtSlot(result=str)
    def getYoloModelLabel(self) -> str:
        """YOLO 모델 라벨 반환 (editor_models/ 자동 감지 포함)"""
        try:
            import os
            from tabs.editor.mosaic_panel import _load_yolo_model_paths
            # _load_yolo_model_paths()가 editor_models/ 내 파일도 자동 감지
            paths = _load_yolo_model_paths()
            if paths:
                names = [os.path.basename(p) for p in paths]
                return ", ".join(names)
        except Exception:
            pass
        return "No Model Loaded"

    @pyqtSlot(result=str)
    def refreshYoloModels(self) -> str:
        """editor_models/ 재스캔 후 라벨 반환"""
        label = self.getYoloModelLabel()
        self.yoloModelUpdated.emit(label)
        return label

    @pyqtSlot(str, result=str)
    def getTagSuggestions(self, prefix: str) -> str:
        """태그 자동완성 후보 반환."""
        try:
            from utils.tag_completer import get_tag_completer
            completer = get_tag_completer()
            # 주의: TagCompleter.get_suggestions의 키워드는 max_count
            suggestions = completer.get_suggestions(prefix, max_count=10)
            return json.dumps(suggestions)
        except Exception as e:
            import traceback
            print(f"[getTagSuggestions] 오류: {e}")
            traceback.print_exc()
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

    # ── 이미지 캡션 (Ollama 비전 모델, taggui 방식 .txt 사이드카) ──
    def _caption_txt_path(self, image_path: str, out_dir: str = '') -> str:
        """캡션 .txt 경로. out_dir 지정+유효 시 그 폴더에 {basename}.txt, 아니면 이미지 옆."""
        import os
        if out_dir and os.path.isdir(out_dir):
            base = os.path.splitext(os.path.basename(image_path))[0]
            return os.path.join(out_dir, base + '.txt')
        return os.path.splitext(image_path)[0] + '.txt'

    @pyqtSlot(str, result=str)
    def captionImage(self, payload_json: str) -> str:
        """단일 이미지 캡션. payload {path, prompt, model, url, save, outDir}. → {caption, txtPath, saved}."""
        try:
            import os
            from core.ollama_client import OllamaClient
            p = json.loads(payload_json) if payload_json else {}
            path = p.get('path', '')
            if not path or not os.path.exists(path):
                return json.dumps({"error": "이미지 경로 없음"})
            model = (p.get('model') or '').strip()
            if not model:
                return json.dumps({"error": "캡션 모델을 지정하세요"})
            url = p.get('url') or 'http://localhost:11434'
            cap = OllamaClient(url, model).caption_image(path, p.get('prompt', ''))
            txt = self._caption_txt_path(path, p.get('outDir', ''))
            saved = False
            if p.get('save', True):
                with open(txt, 'w', encoding='utf-8') as f:
                    f.write(cap)
                saved = True
            return json.dumps({"caption": cap, "txtPath": txt.replace('\\', '/'), "saved": saved},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def startCaptionBatch(self, payload_json: str) -> str:
        """여러 이미지 일괄 캡션 (백그라운드 스레드). payload {files,prompt,model,url,save,overwrite}.
        진행 상황은 captionProgress 시그널, 완료는 captionDone 시그널로 통지."""
        try:
            import os
            import threading
            from core.ollama_client import OllamaClient
            p = json.loads(payload_json) if payload_json else {}
            files = [f for f in (p.get('files') or []) if f and os.path.exists(f)]
            if not files:
                return json.dumps({"error": "대상 이미지 없음"})
            model = (p.get('model') or '').strip()
            if not model:
                return json.dumps({"error": "캡션 모델을 지정하세요"})
            url = p.get('url') or 'http://localhost:11434'
            prompt = p.get('prompt', '')
            save = bool(p.get('save', True))
            overwrite = bool(p.get('overwrite', False))
            out_dir = p.get('outDir', '') or ''
            if out_dir:
                try:
                    os.makedirs(out_dir, exist_ok=True)
                except Exception:
                    pass

            def _emit(d):
                self.captionProgress.emit(json.dumps(d, ensure_ascii=False))

            def _run():
                client = OllamaClient(url, model)
                total, ok, failed = len(files), 0, 0
                for i, path in enumerate(files):
                    txt = self._caption_txt_path(path, out_dir)
                    pn = path.replace('\\', '/')
                    if save and not overwrite and os.path.exists(txt):
                        try:
                            with open(txt, encoding='utf-8') as f:
                                existing = f.read().strip()
                        except Exception:
                            existing = ''
                        ok += 1
                        _emit({"index": i, "total": total, "path": pn, "caption": existing, "skipped": True})
                        continue
                    try:
                        cap = client.caption_image(path, prompt)
                        if save:
                            with open(txt, 'w', encoding='utf-8') as f:
                                f.write(cap)
                        ok += 1
                        _emit({"index": i, "total": total, "path": pn, "caption": cap})
                    except Exception as e:
                        failed += 1
                        _emit({"index": i, "total": total, "path": pn, "error": str(e)})
                self.captionDone.emit(json.dumps({"total": total, "ok": ok, "failed": failed}))

            threading.Thread(target=_run, daemon=True).start()
            return json.dumps({"started": True, "total": len(files)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def loadCaption(self, path: str) -> str:
        """이미지 옆 .txt 사이드카 캡션 읽기 → {caption}."""
        try:
            import os
            txt = os.path.splitext(path)[0] + '.txt'
            if os.path.exists(txt):
                with open(txt, encoding='utf-8') as f:
                    return json.dumps({"caption": f.read().strip()}, ensure_ascii=False)
            return json.dumps({"caption": ""})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def saveCaption(self, payload_json: str) -> str:
        """캡션을 .txt 사이드카로 저장. payload {path, caption, outDir}. → {ok, txtPath}."""
        try:
            import os
            p = json.loads(payload_json) if payload_json else {}
            path = p.get('path', '')
            if not path:
                return json.dumps({"error": "경로 없음"})
            out_dir = p.get('outDir', '') or ''
            if out_dir:
                try:
                    os.makedirs(out_dir, exist_ok=True)
                except Exception:
                    pass
            txt = self._caption_txt_path(path, out_dir)
            with open(txt, 'w', encoding='utf-8') as f:
                f.write(p.get('caption', '') or '')
            return json.dumps({"ok": True, "txtPath": txt.replace('\\', '/')}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def getImageExif(self, filepath: str) -> str:
        """이미지의 EXIF 반환 (구조화된 파라미터 포함)"""
        try:
            from PIL import Image
            import os, re
            clean = _normalize_vue_path(filepath)
            if not clean:
                return json.dumps({'error': '파일을 찾을 수 없습니다', 'path': filepath})
            img = Image.open(clean)
            info = {}
            raw = img.info.get('parameters', img.info.get('prompt', ''))
            info['raw'] = raw
            info['path'] = clean.replace('\\', '/')
            info['filename'] = os.path.basename(clean)
            info['size'] = f"{img.width} × {img.height}"
            if raw and 'Steps:' in raw:
                parts = raw.split('\nNegative prompt: ')
                info['prompt'] = parts[0].strip()
                if len(parts) > 1:
                    sub = parts[1].split('\nSteps: ')
                    info['negative'] = sub[0].strip()
                    if len(sub) > 1:
                        params_raw = 'Steps: ' + sub[1].strip()
                        info['params_line'] = params_raw
                        # 구조화된 파라미터 파싱
                        info['params'] = self._parse_params_line(params_raw)
            return json.dumps(info, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e), 'path': filepath})

    def _parse_params_line(self, params_line: str) -> dict:
        """SD Parameter 라인을 구조화된 딕셔너리로 파싱"""
        import re
        result = {'generation': '', 'model': '', 'hires': '', 'extensions': '', 'other': ''}
        # 개별 파라미터 파싱 (Key: Value 형식)
        params = {}
        for m in re.finditer(r'([A-Za-z][A-Za-z0-9_ ]*?):\s*([^,]+?)(?:,\s*|$)', params_line):
            params[m.group(1).strip()] = m.group(2).strip()

        # Line 1: Steps + Sampler + Scheduler
        gen_parts = []
        for k in ['Steps', 'Sampler', 'Schedule type']:
            if k in params:
                gen_parts.append(f"{k}: {params.pop(k)}")
        result['generation'] = ', '.join(gen_parts)

        # Line 2: CFG, Seed, Size
        core_parts = []
        for k in ['CFG scale', 'Seed', 'Size']:
            if k in params:
                core_parts.append(f"{k}: {params.pop(k)}")
        result['core'] = ', '.join(core_parts)

        # Line 3: Model
        model_parts = []
        for k in ['Model', 'Model hash', 'VAE', 'Clip skip']:
            if k in params:
                model_parts.append(f"{k}: {params.pop(k)}")
        result['model'] = ', '.join(model_parts)

        # Line 4: Hires
        hires_parts = []
        for k in list(params.keys()):
            if k.lower().startswith('hires') or k.lower().startswith('hr ') or 'Denoising strength' == k:
                hires_parts.append(f"{k}: {params.pop(k)}")
        result['hires'] = ', '.join(hires_parts)

        # Line 5: Extensions (ADetailer, SAM3, NegPiP 등)
        ext_parts = []
        for k in list(params.keys()):
            kl = k.lower()
            if any(x in kl for x in ['adetailer', 'sam3', 'negpip', 'controlnet', 'ad_', 'tiled']):
                ext_parts.append(f"{k}: {params.pop(k)}")
        result['extensions'] = ', '.join(ext_parts)

        # 나머지
        other_parts = [f"{k}: {v}" for k, v in params.items()]
        result['other'] = ', '.join(other_parts)

        return result

