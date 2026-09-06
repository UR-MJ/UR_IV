# workers/ollama_worker.py
"""Ollama 비동기 Worker — UI 블로킹 방지"""
from PyQt6.QtCore import QThread, pyqtSignal


class OllamaWorker(QThread):
    finished = pyqtSignal(str)  # JSON {tags, mode}
    error = pyqtSignal(str)

    def __init__(self, base_url: str, model: str, tags: str, mode: str, extra_prompt: str = '', parent=None, *,
                 instruction_feature=None, instructions=None):
        super().__init__(parent)
        from core.ai_assist_instructions import load_instructions, normalize_instructions
        self._base_url = base_url
        self._model = model
        self._tags = tags
        self._mode = mode
        self._extra = extra_prompt
        # Snapshot at request creation, not after the worker starts. Settings
        # edits or mutations of a caller's dict cannot change an in-flight job.
        self._instructions = (load_instructions() if instructions is None
                              else normalize_instructions(instructions))
        self._instruction_feature = instruction_feature

    def run(self):
        try:
            import json
            from core.ollama_client import OllamaClient
            client = OllamaClient(self._base_url, self._model)
            result = client.enhance(self._tags, self._mode, self._extra,
                                    instructions=self._instructions,
                                    instruction_feature=self._instruction_feature)
            self.finished.emit(json.dumps({'tags': result, 'mode': self._mode}))
        except Exception as e:
            self.error.emit(str(e))
