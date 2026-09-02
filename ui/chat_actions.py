"""대화 탭 액션 — Vue `requestAction('chat_*')` 의 Python 쪽.

GeneratorMainUI 에 믹스인으로 얹힌다(`ui/creator_actions.py` 와 같은 방식).
브리지 계약: tests/test_bridge_contract.py 가 아래 `action in (...)` 리터럴에서 이름을
읽어 frontend 의 requestAction 과 대조한다 — 튜플을 변수로 빼면 검사가 눈을 감는다.

시그널(ui/vue_bridge.py): chatToken {id,text} · chatDone {id,ok,content,stopped,error?} ·
chatThreads [threads].
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import os
import re

from core.chat_store import ChatStore, build_ollama_messages, clean_options, inline_image_paths
from workers.chat_worker import ChatWorker

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class ChatActionsMixin:
    _chat_worker: ChatWorker | None = None
    _chat_store: ChatStore | None = None

    def _handle_chat_action(self, action: str, payload: dict) -> bool:
        if action in ("chat_send", "chat_stop", "chat_load", "chat_save", "chat_export"):
            pass
        else:
            return False
        handlers = {
            "chat_send": self._chat_send,
            "chat_stop": self._chat_stop,
            "chat_load": self._chat_load,
            "chat_save": self._chat_save,
            "chat_export": self._chat_export,
        }
        handlers[action](payload or {})
        return True

    # ── 저장 ──
    def _chat_store_instance(self) -> ChatStore:
        if self._chat_store is None:
            self._chat_store = ChatStore()
        return self._chat_store

    def _chat_load(self, _payload: dict) -> None:
        threads = self._chat_store_instance().load()
        self.vue_bridge.chatThreads.emit(json.dumps(threads, ensure_ascii=False))

    def _chat_save(self, payload: dict) -> None:
        self._chat_store_instance().save(payload.get("threads") or [])

    def _chat_export(self, payload: dict) -> None:
        """대화 하나를 Markdown 파일로 — 본문은 Vue 가 만들고 여기서는 저장 대화상자만."""
        from PyQt6.QtWidgets import QFileDialog
        title = re.sub(r'[\\/:*?"<>|]+', ' ', str(payload.get("title") or "")).strip() or "대화"
        path, _ = QFileDialog.getSaveFileName(self, "대화 내보내기", f"{title}.md", "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(str(payload.get("markdown") or ""))
            self.vue_bridge.showNotification.emit("success", f"내보냄: {os.path.basename(path)}")
        except OSError as exc:
            self.vue_bridge.showNotification.emit("error", f"내보내기 실패: {exc}")

    # ── 대화 ──
    def _chat_send(self, payload: dict) -> None:
        request_id = str(payload.get("id") or uuid.uuid4().hex)
        url = str(payload.get("url") or "").strip() or DEFAULT_OLLAMA_URL
        model = str(payload.get("model") or "").strip()
        if not model:
            self.vue_bridge.chatDone.emit(json.dumps({
                "id": request_id, "ok": False, "content": "", "stopped": False,
                "error": "모델이 선택되지 않았습니다 — Settings › AI 어시스트에서 고르세요",
            }, ensure_ascii=False))
            return
        messages = build_ollama_messages(
            inline_image_paths(payload.get("messages") or []),
            system_prompt=str(payload.get("system") or ""),
        )
        options: dict[str, Any] = clean_options(payload.get("options"))
        # 한 번에 하나 — 새 요청이 오면 이전 것을 멈춘다. 둘이 동시에 흐르면 토큰이 섞인다.
        self._chat_stop({})
        # thinking 모델은 기본으로 생각부터 한다 — 빠른 답변이 기본, '깊은 추론' 을 켰을 때만 생각을 흘린다
        think = bool(payload.get("think"))
        worker = ChatWorker(request_id, url, model, messages, options, think=think, parent=self)
        worker.token.connect(self.vue_bridge.chatToken.emit)
        worker.done.connect(self._on_chat_done)
        worker.finished.connect(worker.deleteLater)   # 교체된 옛 워커도 스스로 정리된다
        self._chat_worker = worker
        worker.start()

    def _chat_stop(self, _payload: dict) -> None:
        worker = self._chat_worker
        if worker is not None and worker.isRunning():
            worker.stop()

    def _on_chat_done(self, payload_json: str) -> None:
        self.vue_bridge.chatDone.emit(payload_json)
        # 끝난 것이 *현재* 워커일 때만 비운다 — 새 요청으로 교체된 옛 워커의 done 이 늦게 올 수 있다
        finished = self.sender() if hasattr(self, "sender") else None
        if finished is None or finished is self._chat_worker:
            self._chat_worker = None
