# widgets/stats_panel.py
"""생성 통계 대시보드 다이얼로그"""
import os
from collections import Counter
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton, QProgressBar
)
from PyQt6.QtCore import QThread, pyqtSignal


def _parse_gen_info(text: str) -> dict:
    """PNG parameters 문자열을 파싱하여 dict 반환"""
    params = {}
    try:
        parts = text.split('\nNegative prompt: ')
        prompt = parts[0].strip()
        params_line = ""

        if len(parts) > 1:
            sub = parts[1].split('\nSteps: ')
            if len(sub) > 1:
                params_line = "Steps: " + sub[1].strip()
        else:
            for line in text.split('\n'):
                if line.startswith("Steps: "):
                    params_line = line

        params['prompt'] = prompt

        if params_line:
            for item in params_line.split(', '):
                if ':' in item:
                    k, v = item.split(':', 1)
                    params[k.strip()] = v.strip()
    except Exception:
        params['prompt'] = text.strip()
    return params


class StatsWorker(QThread):
    """EXIF 파싱 워커"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)

    def __init__(self, rows: list):
        super().__init__()
        self._rows = rows

    def run(self):
        model_counter = Counter()
        sampler_counter = Counter()
        tag_counter = Counter()
        resolution_counter = Counter()
        date_counter = Counter()
        steps_list: list[int] = []
        cfg_list: list[float] = []
        total = len(self._rows)

        for i, (path, exif_text) in enumerate(self._rows):
            if i % 50 == 0:
                self.progress.emit(i, total)
            params = _parse_gen_info(exif_text)

            # 모델
            model = params.get('Model', '')
            if model:
                model_counter[model] += 1

            # 샘플러
            sampler = params.get('Sampler', '')
            if sampler:
                sampler_counter[sampler] += 1

            # Steps / CFG
            try:
                steps_list.append(int(params.get('Steps', 0)))
            except (ValueError, TypeError):
                pass
            try:
                cfg_list.append(float(params.get('CFG scale', 0)))
            except (ValueError, TypeError):
                pass

            # 해상도
            size = params.get('Size', '')
            if size:
                resolution_counter[size] += 1

            # 태그
            prompt = params.get('prompt', '')
            if prompt:
                tags = [t.strip() for t in prompt.split(',') if t.strip()]
                for tag in tags:
                    tag_counter[tag] += 1

            # 날짜 (파일 수정 시간 기반)
            try:
                real_path = path.replace('/', os.sep)
                if not os.path.isabs(real_path) and real_path.startswith(os.sep):
                    real_path = real_path[1:]  # normalize_path 보정
                mtime = os.path.getmtime(real_path)
                date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                date_counter[date_str] += 1
            except Exception:
                pass

        result = {
            'total_images': total,
            'models': model_counter.most_common(),
            'samplers': sampler_counter.most_common(),
            'tags_top30': tag_counter.most_common(30),
            'resolutions': resolution_counter.most_common(),
            'steps': steps_list,
            'cfg': cfg_list,
            'timeline': sorted(date_counter.items()),
        }
        self.finished.emit(result)


class StatsPanel(QDialog):
    """생성 통계 대시보드"""

    def __init__(self, db, folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("생성 통계")
        self.setMinimumSize(600, 700)
        self.resize(700, 800)
        self.setStyleSheet("background-color: #1E1E1E; color: #EEE;")

        self._db = db
        self._folder = folder
        self._worker: StatsWorker | None = None

        self._setup_ui()
        self._load_stats()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel("📊 생성 통계 대시보드")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #5865F2;")
        layout.addWidget(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2C2C2C; border: 1px solid #555;
                border-radius: 4px; text-align: center; color: #AAA; font-size: 11px;
            }
            QProgressBar::chunk { background-color: #5865F2; border-radius: 3px; }
        """)
        layout.addWidget(self.progress_bar)

        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setStyleSheet(
            "background-color: #252525; color: #DDD; border: 1px solid #444; "
            "border-radius: 4px; font-family: 'Consolas'; font-size: 11px; padding: 8px;"
        )
        layout.addWidget(self.stats_text, stretch=1)

        btn_close = QPushButton("닫기")
        btn_close.setFixedHeight(35)
        btn_close.setStyleSheet(
            "background-color: #333; color: #AAA; border-radius: 4px; font-size: 13px;"
        )
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def _load_stats(self):
        from core.database import normalize_path
        norm_folder = normalize_path(self._folder)
        rows = self._db.get_all_exif_in_folder(norm_folder)

        if not rows:
            self.stats_text.setHtml(
                "<span style='color:#888;'>EXIF 데이터가 있는 이미지가 없습니다.</span>"
            )
            self.progress_bar.hide()
            return

        self.progress_bar.setRange(0, len(rows))
        self._worker = StatsWorker(rows)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)

    def _on_finished(self, result: dict):
        self.progress_bar.hide()
        self._render_stats(result)

    def _render_stats(self, r: dict):
        html = "<h2 style='color:#5865F2;'>생성 통계 요약</h2>"
        html += f"<p>총 이미지 수: <b>{r['total_images']}</b></p>"

        # Steps 통계
        steps = r['steps']
        if steps:
            html += (
                f"<p>Steps — 평균: <b>{sum(steps)/len(steps):.1f}</b>, "
                f"최소: <b>{min(steps)}</b>, 최대: <b>{max(steps)}</b></p>"
            )

        # CFG 통계
        cfg = r['cfg']
        if cfg:
            html += (
                f"<p>CFG — 평균: <b>{sum(cfg)/len(cfg):.2f}</b>, "
                f"최소: <b>{min(cfg):.1f}</b>, 최대: <b>{max(cfg):.1f}</b></p>"
            )

        # 모델 테이블
        html += self._make_table("모델별 사용 횟수", r['models'])
        html += self._make_table("샘플러별 사용 횟수", r['samplers'])
        html += self._make_table("해상도 분포", r['resolutions'])
        html += self._make_table("자주 쓴 태그 Top 30", r['tags_top30'])

        # 타임라인
        timeline = r.get('timeline', [])
        if timeline:
            html += "<h3 style='color:#AAA; margin-top:12px;'>날짜별 생성 타임라인</h3>"
            max_count = max(c for _, c in timeline) if timeline else 1
            for date_str, count in timeline[-30:]:  # 최근 30일만
                bar_w = int(count / max_count * 300)
                html += (
                    f"<div style='margin:1px 0; display:flex; align-items:center;'>"
                    f"<span style='color:#888; width:90px; display:inline-block; "
                    f"font-size:11px;'>{date_str}</span>"
                    f"<span style='background:#5865F2; height:16px; width:{max(2, bar_w)}px; "
                    f"display:inline-block; border-radius:3px; margin:0 6px;'></span>"
                    f"<span style='color:#AAA; font-size:11px;'>{count}장</span>"
                    f"</div>"
                )

        self.stats_text.setHtml(html)

    def _make_table(self, title: str, items: list) -> str:
        if not items:
            return ""
        html = f"<h3 style='color:#AAA; margin-top:12px;'>{title}</h3>"
        html += (
            "<table style='width:100%; border-collapse:collapse;'>"
            "<tr style='border-bottom:1px solid #555;'>"
            "<th style='text-align:left; padding:3px 6px; color:#888;'>항목</th>"
            "<th style='text-align:right; padding:3px 6px; color:#888;'>횟수</th>"
            "</tr>"
        )
        for name, count in items:
            html += (
                f"<tr style='border-bottom:1px solid #333;'>"
                f"<td style='padding:2px 6px;'>{name}</td>"
                f"<td style='text-align:right; padding:2px 6px; color:#5865F2;'>{count}</td>"
                f"</tr>"
            )
        html += "</table>"
        return html
