# workers/ollama_worker.py
"""Ollama 비동기 Worker — UI 블로킹 방지"""
from PyQt6.QtCore import QThread, pyqtSignal


class OllamaWorker(QThread):
    finished = pyqtSignal(str)  # JSON {tags, mode}
    error = pyqtSignal(str)

    def __init__(self, base_url: str, model: str, tags: str, mode: str, extra_prompt: str = '', parent=None):
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._tags = tags
        self._mode = mode
        self._extra = extra_prompt

    def run(self):
        try:
            import json
            from core.ollama_client import OllamaClient
            client = OllamaClient(self._base_url, self._model)
            result = client.enhance(self._tags, self._mode, self._extra)
            self.finished.emit(json.dumps({'tags': result, 'mode': self._mode}))
        except Exception as e:
            self.error.emit(str(e))
