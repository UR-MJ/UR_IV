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
