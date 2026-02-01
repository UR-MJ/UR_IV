# widgets/queue_manager.py
"""
대기열 로직 관리 (자동화 연동)
"""
import time
from PyQt6.QtCore import QObject, pyqtSignal


class QueueManager(QObject):
    """대기열 관리자"""

    # 시그널
    need_new_prompt = pyqtSignal()
    generation_requested = pyqtSignal(dict)
    queue_completed = pyqtSignal(int)

    def __init__(self, queue_panel, parent=None):
        super().__init__(parent)
        self.queue_panel = queue_panel
        self.is_running = False
        self.generated_count = 0
        self.total_count = 0
        self.delay_seconds = 1.0

        # 배치 리포트용
        self._batch_start_time: float = 0.0
        self._success_count: int = 0
        self._fail_count: int = 0
        self._gen_times: list[float] = []
        self._current_gen_start: float = 0.0

        # 시그널 연결
        self.queue_panel.start_requested.connect(self.start)
        self.queue_panel.stop_requested.connect(self.stop)

    def start(self):
        """자동화 시작"""
        if self.queue_panel.is_empty():
            self.need_new_prompt.emit()

        self.is_running = True
        self.generated_count = 0
        self.total_count = self.queue_panel.count()

        # 배치 카운터 초기화
        self._batch_start_time = time.time()
        self._success_count = 0
        self._fail_count = 0
        self._gen_times.clear()

        self.queue_panel.update_progress(0, self.total_count)
        self._process_next()

    def stop(self):
        """자동화 중지"""
        self.is_running = False
        self.queue_panel.set_processing(False)
        self.queue_panel.reset_progress()
        self.queue_completed.emit(self.generated_count)

    def _process_next(self):
        """다음 아이템 처리"""
        if not self.is_running:
            return

        item = self.queue_panel.get_first_item()

        if not item:
            # 큐가 비었으면 자연 완료
            if self.generated_count > 0:
                self.stop()
                return
            self.need_new_prompt.emit()
            return

        self._current_gen_start = time.time()
        self.queue_panel.set_processing(True, item['id'])
        self.generation_requested.emit(item)

    def on_generation_completed(self, success: bool):
        """생성 완료 콜백"""
        if not self.is_running:
            return

        # 생성 시간 기록
        gen_elapsed = time.time() - self._current_gen_start
        self._gen_times.append(gen_elapsed)
        if success:
            self._success_count += 1
        else:
            self._fail_count += 1

        current_item = self.queue_panel.get_first_item()
        is_last_of_group = current_item.get('is_last_of_group', True) if current_item else True

        self.queue_panel.remove_first_item()
        self.generated_count += 1
        self.queue_panel.update_progress(self.generated_count, self.total_count)

        from PyQt6.QtCore import QTimer

        delay_ms = int(self.delay_seconds * 1000)

        def continue_processing():
            if not self.is_running:
                return

            if self.queue_panel.is_empty() and is_last_of_group:
                # 큐가 비어있고 마지막 그룹 → 자연 완료
                self.stop()
            else:
                self._process_next()

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, continue_processing)
        else:
            continue_processing()

    def get_batch_report(self) -> dict:
        """배치 리포트 반환"""
        total_elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0.0
        avg_time = sum(self._gen_times) / len(self._gen_times) if self._gen_times else 0.0
        return {
            'total': self._success_count + self._fail_count,
            'success': self._success_count,
            'fail': self._fail_count,
            'elapsed': total_elapsed,
            'avg_time': avg_time,
        }

    def add_prompt_group(self, prompt_data: dict, repeat_count: int = 1):
        """프롬프트 그룹 추가"""
        self.queue_panel.add_items_as_group([prompt_data], repeat_count)
        self.total_count += repeat_count

        if self.is_running and self.queue_panel.count() == repeat_count:
            self._process_next()

    def set_delay(self, seconds: float):
        """대기 시간 설정"""
        self.delay_seconds = seconds
