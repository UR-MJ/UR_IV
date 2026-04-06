# ui/vue_bridge.py
"""
PyQt6 ↔ Vue 통신 브릿지 (QWebChannel)
T2I 뷰어 패널의 백엔드 역할
"""
import json
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class VueBridge(QObject):
    """Vue 프론트엔드와 통신하는 브릿지 객체"""

    # Python → Vue 시그널 (JS에서 backend.signalName.connect(callback)으로 수신)
    imageGenerated = pyqtSignal(str)    # JSON: {path, width, height, seed}
    generationStarted = pyqtSignal()
    generationError = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    # ── Python에서 호출하는 메서드 (Vue로 데이터 전송) ──

    def send_image(self, path: str, width: int, height: int, seed: int):
        """생성된 이미지 정보를 Vue로 전송"""
        data = json.dumps({
            'path': path.replace('\\', '/'),
            'width': width,
            'height': height,
            'seed': seed,
        })
        self.imageGenerated.emit(data)

    def send_start(self):
        """생성 시작 알림"""
        self.generationStarted.emit()

    def send_error(self, msg: str):
        """에러 알림"""
        self.generationError.emit(msg)

    # ── Vue에서 호출하는 슬롯 (JS → Python) ──

    @pyqtSlot(result=str)
    def getSettings(self) -> str:
        """현재 생성 설정 반환"""
        return json.dumps({'status': 'ok'})
