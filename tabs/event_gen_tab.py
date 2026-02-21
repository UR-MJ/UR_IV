# tabs/event_gen_tab.py
"""
이벤트 시퀀스 생성 탭 - variant_set 기반 스토리 모드

개선사항:
A. 유사도 기반 프롬프트 검색 (단일 프롬프트 입력 → 가장 근접한 이벤트 매칭)
B. 이전 스텝 기준 diff (스토리 진행감)
C. Children ID순 정렬 (스토리 순서 보장)
D. 최종 프롬프트 미리보기 패널
E. 스텝별 프롬프트 편집 (태그 추가/제거)
F. 백그라운드 데이터 로딩 (QThread)
G. 랜덤 이벤트 선택 버튼
"""
import os
import json
import random
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QGroupBox, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QFrame, QComboBox, QMessageBox, QProgressBar, QTabWidget,
    QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

from core.event_data_loader import EventDataLoader
from widgets.common_widgets import NoScrollSpinBox
from utils.theme_manager import get_color


# ──────────────────────────────────────────────────────
#  F. 백그라운드 데이터 로딩 워커
# ──────────────────────────────────────────────────────

class EventDataLoadWorker(QThread):
    """Parquet 데이터를 백그라운드에서 로드"""
    finished = pyqtSignal(object)  # EventDataLoader 또는 에러 문자열
    progress = pyqtSignal(str)

    def __init__(self, parquet_dir, ratings):
        super().__init__()
        self.parquet_dir = parquet_dir
        self.ratings = ratings

    def run(self):
        try:
            self.progress.emit("데이터 로딩 중...")
            loader = EventDataLoader(self.parquet_dir)
            loader.load_parquets_by_rating(
                self.ratings,
                progress_callback=lambda cur, total, name: self.progress.emit(
                    f"로딩 중... ({cur}/{total}) {name}"
                )
            )
            self.finished.emit(loader)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(f"오류: {e}")


# ──────────────────────────────────────────────────────
#  E. 편집 가능한 StepCard
# ──────────────────────────────────────────────────────

class StepCard(QWidget):
    """스텝 카드 위젯 - 개별 스텝 정보 + 캐리 옵션 + 편집"""

    carry_changed = pyqtSignal(int)
    tags_edited = pyqtSignal(int, set)  # step_index, new_tags

    def __init__(self, step_data: dict, parent=None):
        super().__init__(parent)
        self.step_data = step_data
        self.step_index = step_data.get('step', 0)
        self.is_editing = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.setMinimumWidth(200)
        self.setMaximumWidth(240)
        self.setMinimumHeight(320)

        is_parent = self.step_data.get('is_parent', False)

        if is_parent:
            border_color = get_color('accent')
            header_text = "Step 0 (Parent)"
        else:
            border_color = get_color('border')
            header_text = f"Step {self.step_index}"

        self.setStyleSheet(f"""
            StepCard {{
                background-color: {get_color('bg_tertiary')};
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
        """)

        # 헤더
        header_row = QHBoxLayout()
        header = QLabel(header_text)
        header.setStyleSheet(f"color: {border_color}; font-weight: bold; font-size: 12px;")
        header_row.addWidget(header)

        # ★ E. 편집 버튼
        self.btn_edit = QPushButton("✏️")
        self.btn_edit.setFixedSize(34, 34)
        self.btn_edit.setStyleSheet(f"""
            QPushButton {{ border: 1px solid {get_color('border')}; border-radius: 4px; font-size: 12px; background: {get_color('bg_input')}; }}
            QPushButton:hover {{ background: {get_color('bg_button_hover')}; border-color: {get_color('text_muted')}; }}
        """)
        self.btn_edit.setToolTip("태그 편집")
        self.btn_edit.clicked.connect(self._toggle_edit)
        header_row.addWidget(self.btn_edit)
        layout.addLayout(header_row)

        # Rating + Score
        rating = self.step_data.get('rating', '?')
        score = self.step_data.get('score', 0)
        info_label = QLabel(f"Rating: {rating.upper()}  Score: {score}")
        info_label.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 9px;")
        layout.addWidget(info_label)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {get_color('border')};")
        layout.addWidget(line)

        if is_parent:
            tags_label = QLabel("베이스 태그:")
            tags_label.setStyleSheet(f"color: {get_color('accent')}; font-size: 10px;")
            layout.addWidget(tags_label)

            tags_preview = self.step_data.get('tags_str', '')[:120]
            if len(self.step_data.get('tags_str', '')) > 120:
                tags_preview += '...'

            self.tags_display = QLabel(tags_preview)
            self.tags_display.setWordWrap(True)
            self.tags_display.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 9px;")
            self.tags_display.setMaximumHeight(60)
            layout.addWidget(self.tags_display)
        else:
            # ★ B. 이전 스텝 기준 diff 표시
            added = self.step_data.get('added', [])
            removed = self.step_data.get('removed', [])

            added_label = QLabel(f"+ 이전 대비 추가 ({len(added)})")
            added_label.setStyleSheet("color: #27ae60; font-size: 10px; font-weight: bold;")
            layout.addWidget(added_label)

            added_preview = ', '.join(added[:6])
            if len(added) > 6:
                added_preview += f' ... (+{len(added) - 6})'
            self.added_text = QLabel(added_preview or "(없음)")
            self.added_text.setWordWrap(True)
            self.added_text.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 9px;")
            self.added_text.setMaximumHeight(35)
            layout.addWidget(self.added_text)

            removed_label = QLabel(f"- 이전 대비 제거 ({len(removed)})")
            removed_label.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold;")
            layout.addWidget(removed_label)

            removed_preview = ', '.join(removed[:6])
            if len(removed) > 6:
                removed_preview += f' ... (+{len(removed) - 6})'
            self.removed_text = QLabel(removed_preview or "(없음)")
            self.removed_text.setWordWrap(True)
            self.removed_text.setStyleSheet(f"color: {get_color('text_muted')}; font-size: 9px;")
            self.removed_text.setMaximumHeight(35)
            layout.addWidget(self.removed_text)

            self.tags_display = None

        # ★ E. 편집용 텍스트 에디터 (기본 숨김)
        self.edit_area = QTextEdit()
        self.edit_area.setPlaceholderText("태그를 쉼표로 구분하여 편집")
        self.edit_area.setStyleSheet(f"font-size: 9px; background: {get_color('bg_primary')}; color: {get_color('text_primary')};")
        self.edit_area.setMaximumHeight(60)
        self.edit_area.hide()
        layout.addWidget(self.edit_area)

        self.btn_apply_edit = QPushButton("적용")
        self.btn_apply_edit.setFixedHeight(28)
        self.btn_apply_edit.setStyleSheet("font-size: 9px; background: #27ae60; color: white; border-radius: 3px;")
        self.btn_apply_edit.clicked.connect(self._apply_edit)
        self.btn_apply_edit.hide()
        layout.addWidget(self.btn_apply_edit)

        # 구분선
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"background-color: {get_color('border')};")
        layout.addWidget(line2)

        # 캐리 옵션
        carry_label = QLabel("→ 다음으로 캐리:")
        carry_label.setStyleSheet("color: #FFC107; font-size: 10px; font-weight: bold;")
        layout.addWidget(carry_label)

        self.chk_carry_costume = QCheckBox("의상 유지")
        self.chk_carry_costume.setChecked(True)
        self.chk_carry_costume.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 10px;")
        self.chk_carry_costume.toggled.connect(lambda: self.carry_changed.emit(self.step_index))
        layout.addWidget(self.chk_carry_costume)

        self.chk_carry_background = QCheckBox("배경 유지")
        self.chk_carry_background.setChecked(True)
        self.chk_carry_background.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 10px;")
        self.chk_carry_background.toggled.connect(lambda: self.carry_changed.emit(self.step_index))
        layout.addWidget(self.chk_carry_background)

        self.chk_carry_appearance = QCheckBox("외모 유지")
        self.chk_carry_appearance.setChecked(True)
        self.chk_carry_appearance.setStyleSheet(f"color: {get_color('text_primary')}; font-size: 10px;")
        self.chk_carry_appearance.toggled.connect(lambda: self.carry_changed.emit(self.step_index))
        layout.addWidget(self.chk_carry_appearance)

        layout.addStretch()

    def _toggle_edit(self):
        """편집 모드 토글"""
        self.is_editing = not self.is_editing
        if self.is_editing:
            tags = self.step_data.get('tags', set())
            self.edit_area.setPlainText(', '.join(sorted(tags)))
            self.edit_area.show()
            self.btn_apply_edit.show()
            self.btn_edit.setText("❌")
            self.btn_edit.setStyleSheet(f"""
                QPushButton {{ border: 2px solid #e74c3c; border-radius: 4px; font-size: 12px; background: {get_color('bg_tertiary')}; }}
                QPushButton:hover {{ background: {get_color('bg_button_hover')}; }}
            """)
        else:
            self.edit_area.hide()
            self.btn_apply_edit.hide()
            self.btn_edit.setText("✏️")
            self.btn_edit.setStyleSheet(f"""
                QPushButton {{ border: 1px solid {get_color('border')}; border-radius: 4px; font-size: 12px; background: {get_color('bg_tertiary')}; }}
                QPushButton:hover {{ background: {get_color('bg_button_hover')}; border-color: {get_color('text_muted')}; }}
            """)

    def _apply_edit(self):
        """편집 적용"""
        text = self.edit_area.toPlainText()
        new_tags = set(
            t.strip().lower() for t in text.split(',') if t.strip()
        )
        self.step_data['tags'] = new_tags
        self.step_data['tags_str'] = ', '.join(sorted(new_tags))

        # 표시 업데이트
        if self.tags_display:
            preview = self.step_data['tags_str'][:120]
            if len(self.step_data['tags_str']) > 120:
                preview += '...'
            self.tags_display.setText(preview)

        self.tags_edited.emit(self.step_index, new_tags)
        self._toggle_edit()

    def get_carry_options(self) -> dict:
        return {
            'costume': self.chk_carry_costume.isChecked(),
            'background': self.chk_carry_background.isChecked(),
            'appearance': self.chk_carry_appearance.isChecked(),
        }


# ──────────────────────────────────────────────────────
#  메인 탭
# ──────────────────────────────────────────────────────

class EventGenTab(QWidget):
    """이벤트 시퀀스 생성 탭 (개선 버전)"""

    send_to_queue_signal = pyqtSignal(list)

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.event_loader = None
        self.search_results = []
        self.selected_event = None
        self.steps = []
        self.step_cards = []
        self.load_worker = None

        self._setup_ui()
        self._connect_signals()
        self._auto_load_settings()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        left_panel = self._create_search_panel()
        left_panel.setFixedWidth(380)

        right_panel = self._create_result_panel()

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

    def _create_search_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("🎬 스토리 모드 - 이벤트 시퀀스")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {get_color('accent')};")
        layout.addWidget(title)

        # 데이터 로드
        load_group = QGroupBox("데이터 로드")
        load_layout = QVBoxLayout(load_group)

        rating_layout = QHBoxLayout()
        rating_layout.addWidget(QLabel("Rating:"))
        self.chk_rating_g = QCheckBox("G")
        self.chk_rating_s = QCheckBox("S")
        self.chk_rating_q = QCheckBox("Q")
        self.chk_rating_e = QCheckBox("E")
        self.chk_rating_e.setChecked(True)
        for chk in [self.chk_rating_g, self.chk_rating_s, self.chk_rating_q, self.chk_rating_e]:
            rating_layout.addWidget(chk)
        rating_layout.addStretch()
        load_layout.addLayout(rating_layout)

        self.btn_load_data = QPushButton("📥 데이터 로드")
        self.btn_load_data.setFixedHeight(35)
        self.btn_load_data.setStyleSheet(f"""
            QPushButton {{ background-color: {get_color('accent')}; color: white; font-weight: bold; border-radius: 5px; }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """)
        load_layout.addWidget(self.btn_load_data)

        self.load_status_label = QLabel("데이터 미로드")
        self.load_status_label.setStyleSheet(f"color: {get_color('text_muted')};")
        load_layout.addWidget(self.load_status_label)

        layout.addWidget(load_group)

        # ★ A. 프롬프트 기반 검색 (핵심 개선)
        search_group = QGroupBox("🔍 프롬프트 검색")
        search_layout = QVBoxLayout(search_group)

        search_layout.addWidget(QLabel("프롬프트 입력 (가장 근접한 이벤트를 찾습니다):"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setFixedHeight(55)
        self.prompt_input.setPlaceholderText(
            "1girl, long hair, school uniform, classroom, sitting\n"
            "(쉼표로 구분, 태그를 많이 넣을수록 정확도 향상)"
        )
        search_layout.addWidget(self.prompt_input)

        # 제외 태그
        exc_row = QHBoxLayout()
        exc_row.addWidget(QLabel("제외:"))
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("furry, monster")
        exc_row.addWidget(self.exclude_input)
        search_layout.addLayout(exc_row)

        # Child 필터 (접힌 상태)
        self.child_filter_toggle = QCheckBox("Child 필터 (고급)")
        self.child_filter_toggle.setStyleSheet(
            f"color: {get_color('text_secondary')}; font-size: 11px; font-weight: bold;"
        )
        search_layout.addWidget(self.child_filter_toggle)

        self.child_filter_container = QWidget()
        cf_layout = QVBoxLayout(self.child_filter_container)
        cf_layout.setContentsMargins(10, 4, 0, 4)
        cf_layout.setSpacing(4)

        cf_inc_row = QHBoxLayout()
        cf_inc_label = QLabel("포함:")
        cf_inc_label.setFixedWidth(35)
        cf_inc_label.setStyleSheet("color: #8BC34A; font-weight: bold;")
        cf_inc_row.addWidget(cf_inc_label)
        self.child_include_input = QLineEdit()
        self.child_include_input.setPlaceholderText("sex, penetration")
        self.child_include_input.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px 6px;"
        )
        cf_inc_row.addWidget(self.child_include_input)
        cf_layout.addLayout(cf_inc_row)

        cf_exc_row = QHBoxLayout()
        cf_exc_label = QLabel("제외:")
        cf_exc_label.setFixedWidth(35)
        cf_exc_label.setStyleSheet("color: #F44336; font-weight: bold;")
        cf_exc_row.addWidget(cf_exc_label)
        self.child_exclude_input = QLineEdit()
        self.child_exclude_input.setPlaceholderText("futanari, yaoi")
        self.child_exclude_input.setStyleSheet(
            f"background-color: {get_color('bg_input')}; color: {get_color('text_primary')}; border: 1px solid {get_color('border')}; "
            "border-radius: 4px; padding: 4px 6px;"
        )
        cf_exc_row.addWidget(self.child_exclude_input)
        cf_layout.addLayout(cf_exc_row)

        self.child_filter_container.hide()
        search_layout.addWidget(self.child_filter_container)

        layout.addWidget(search_group)

        # 이벤트 길이
        length_group = QGroupBox("이벤트 설정")
        length_layout = QVBoxLayout(length_group)

        len_row = QHBoxLayout()
        len_row.addWidget(QLabel("스텝 수:"))
        self.min_children_spin = NoScrollSpinBox()
        self.min_children_spin.setRange(1, 50)
        self.min_children_spin.setValue(2)
        len_row.addWidget(self.min_children_spin)
        len_row.addWidget(QLabel("~"))
        self.max_children_spin = NoScrollSpinBox()
        self.max_children_spin.setRange(1, 100)
        self.max_children_spin.setValue(10)
        len_row.addWidget(self.max_children_spin)
        length_layout.addLayout(len_row)

        layout.addWidget(length_group)

        # 결과 제한 옵션
        self.chk_limit_results = QCheckBox("상위 100개만 표시")
        self.chk_limit_results.setChecked(True)
        self.chk_limit_results.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 10px;")
        layout.addWidget(self.chk_limit_results)

        # 검색 버튼 행
        btn_row = QHBoxLayout()

        self.btn_search = QPushButton("🔍 유사도 검색")
        self.btn_search.setFixedHeight(45)
        self.btn_search.setEnabled(False)
        self.btn_search.setStyleSheet(f"""
            QPushButton {{ background-color: #27ae60; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }}
            QPushButton:hover {{ background-color: #2ecc71; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """)
        btn_row.addWidget(self.btn_search)

        # ★ G. 랜덤 선택 버튼
        self.btn_random = QPushButton("🎲")
        self.btn_random.setFixedSize(45, 45)
        self.btn_random.setEnabled(False)
        self.btn_random.setToolTip("검색 결과에서 랜덤 선택")
        self.btn_random.setStyleSheet(f"""
            QPushButton {{ background-color: #e67e22; color: white; font-weight: bold; font-size: 18px; border-radius: 5px; }}
            QPushButton:hover {{ background-color: #f39c12; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """)
        btn_row.addWidget(self.btn_random)

        layout.addLayout(btn_row)

        self.search_status_label = QLabel("검색 결과: 0개")
        self.search_status_label.setStyleSheet(f"color: {get_color('text_muted')};")
        layout.addWidget(self.search_status_label)

        layout.addStretch()

        # 설정 저장/불러오기
        save_row = QHBoxLayout()
        self.btn_save_settings = QPushButton("💾 설정 저장")
        self.btn_save_settings.setFixedHeight(36)
        self.btn_save_settings.setStyleSheet("font-size: 11px;")
        self.btn_save_settings.clicked.connect(self._save_settings)
        save_row.addWidget(self.btn_save_settings)

        self.btn_load_settings = QPushButton("📂 설정 불러오기")
        self.btn_load_settings.setFixedHeight(36)
        self.btn_load_settings.setStyleSheet("font-size: 11px;")
        self.btn_load_settings.clicked.connect(self._load_settings)
        save_row.addWidget(self.btn_load_settings)
        layout.addLayout(save_row)

        return panel

    def _create_result_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 검색 결과 목록
        result_group = QGroupBox("검색된 이벤트 (유사도순)")
        result_layout = QVBoxLayout(result_group)

        self.result_list = QListWidget()
        self.result_list.setMinimumHeight(180)
        self.result_list.setStyleSheet(f"""
            QListWidget {{ background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')}; border-radius: 5px; }}
            QListWidget::item {{ padding: 6px; border-bottom: 1px solid {get_color('bg_input')}; }}
            QListWidget::item:selected {{ background-color: {get_color('accent')}; }}
        """)
        result_layout.addWidget(self.result_list)
        layout.addWidget(result_group)

        # 스텝 카드들 (세로 스크롤, 가로로 줄바꿈)
        steps_group = QGroupBox("🎬 스토리 스텝 (← 이전 스텝 대비 변화 표시)")
        steps_layout = QVBoxLayout(steps_group)

        self.steps_scroll = QScrollArea()
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.steps_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.steps_scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {get_color('bg_primary')}; border: 1px solid {get_color('border')}; border-radius: 5px; }}
        """)

        self.steps_container = QWidget()
        self.steps_flow_layout = QVBoxLayout(self.steps_container)
        self.steps_flow_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.steps_flow_layout.setSpacing(6)
        self.steps_flow_layout.setContentsMargins(10, 10, 10, 10)

        self.steps_scroll.setWidget(self.steps_container)
        steps_layout.addWidget(self.steps_scroll)
        layout.addWidget(steps_group, 1)

        # ★ D. 최종 프롬프트 미리보기 + 생성 옵션
        bottom_tabs = QTabWidget()
        bottom_tabs.setFixedHeight(180)
        bottom_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {get_color('border')}; background: {get_color('bg_primary')}; border-radius: 5px; }}
            QTabBar::tab {{ background: {get_color('bg_tertiary')}; color: {get_color('text_muted')}; padding: 6px 15px; }}
            QTabBar::tab:selected {{ background: {get_color('bg_button')}; color: {get_color('text_primary')}; border-bottom: 2px solid {get_color('accent')}; }}
        """)

        # 탭 1: 생성 옵션
        options_widget = QWidget()
        options_layout = QVBoxLayout(options_widget)
        options_layout.setContentsMargins(8, 8, 8, 8)

        options_row1 = QHBoxLayout()
        self.chk_fix_seed = QCheckBox("시드 고정 (일관성 유지)")
        self.chk_fix_seed.setChecked(True)
        options_row1.addWidget(self.chk_fix_seed)

        self.chk_use_t2i_settings = QCheckBox("T2I 설정 사용 (선행/후행/작가)")
        self.chk_use_t2i_settings.setChecked(True)
        options_row1.addWidget(self.chk_use_t2i_settings)
        options_row1.addStretch()
        options_layout.addLayout(options_row1)

        repeat_row = QHBoxLayout()
        repeat_row.addWidget(QLabel("스텝당 반복:"))
        self.repeat_spin = NoScrollSpinBox()
        self.repeat_spin.setRange(1, 10)
        self.repeat_spin.setValue(1)
        repeat_row.addWidget(self.repeat_spin)
        repeat_row.addStretch()
        self.total_images_label = QLabel("총 0장 생성 예정")
        self.total_images_label.setStyleSheet("color: #FFC107; font-weight: bold;")
        repeat_row.addWidget(self.total_images_label)
        options_layout.addLayout(repeat_row)

        gen_btn_row = QHBoxLayout()
        self.btn_add_to_queue = QPushButton("🚀 대기열에 추가")
        self.btn_add_to_queue.setFixedHeight(40)
        self.btn_add_to_queue.setEnabled(False)
        self.btn_add_to_queue.setStyleSheet(f"""
            QPushButton {{ background-color: {get_color('accent')}; color: white; font-weight: bold; border-radius: 5px; }}
            QPushButton:hover {{ background-color: {get_color('bg_button_hover')}; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """)
        gen_btn_row.addWidget(self.btn_add_to_queue)

        self.btn_generate_now = QPushButton("▶ 바로 생성")
        self.btn_generate_now.setFixedHeight(40)
        self.btn_generate_now.setEnabled(False)
        self.btn_generate_now.setStyleSheet(f"""
            QPushButton {{ background-color: #27ae60; color: white; font-weight: bold; border-radius: 5px; }}
            QPushButton:hover {{ background-color: #2ecc71; }}
            QPushButton:disabled {{ background-color: {get_color('bg_button')}; color: {get_color('text_muted')}; }}
        """)
        gen_btn_row.addWidget(self.btn_generate_now)
        options_layout.addLayout(gen_btn_row)

        bottom_tabs.addTab(options_widget, "⚙️ 생성 옵션")

        # ★ D. 탭 2: 최종 프롬프트 미리보기
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(8, 8, 8, 8)

        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setStyleSheet(
            f"font-family: Consolas; font-size: 9pt; background: {get_color('bg_primary')}; color: {get_color('text_secondary')};"
        )
        self.prompt_preview.setPlaceholderText(
            "이벤트를 선택하면 각 스텝의 최종 프롬프트가 여기에 표시됩니다."
        )
        preview_layout.addWidget(self.prompt_preview)

        bottom_tabs.addTab(preview_widget, "📋 프롬프트 미리보기")

        layout.addWidget(bottom_tabs)

        return panel

    def _connect_signals(self):
        self.btn_load_data.clicked.connect(self._on_load_data)
        self.btn_search.clicked.connect(self._on_search)
        self.btn_random.clicked.connect(self._on_random_select)
        self.result_list.itemClicked.connect(self._on_event_selected)
        self.btn_add_to_queue.clicked.connect(self._on_add_to_queue)
        self.btn_generate_now.clicked.connect(self._on_generate_now)
        self.repeat_spin.valueChanged.connect(self._update_total_count)
        self.child_filter_toggle.toggled.connect(self.child_filter_container.setVisible)

    # ──────────────────────────────────────────────────────
    #  F. 백그라운드 데이터 로딩
    # ──────────────────────────────────────────────────────

    def _on_load_data(self):
        ratings = []
        if self.chk_rating_g.isChecked(): ratings.append('g')
        if self.chk_rating_s.isChecked(): ratings.append('s')
        if self.chk_rating_q.isChecked(): ratings.append('q')
        if self.chk_rating_e.isChecked(): ratings.append('e')

        if not ratings:
            QMessageBox.warning(self, "경고", "최소 하나의 Rating을 선택하세요.")
            return

        from config import EVENT_PARQUET_DIR

        self.btn_load_data.setEnabled(False)
        self.btn_load_data.setText("⏳ 로딩 중...")
        self.load_status_label.setText("백그라운드 로딩 중...")

        # ★ F. 백그라운드 스레드로 로딩
        self.load_worker = EventDataLoadWorker(EVENT_PARQUET_DIR, ratings)
        self.load_worker.progress.connect(
            lambda msg: self.load_status_label.setText(msg)
        )
        self.load_worker.finished.connect(self._on_load_finished)
        self.load_worker.start()

    def _on_load_finished(self, result):
        self.btn_load_data.setEnabled(True)
        self.btn_load_data.setText("📥 데이터 로드")

        if isinstance(result, str):
            QMessageBox.critical(self, "오류", f"데이터 로드 실패:\n{result}")
            self.load_status_label.setText(f"❌ 로드 실패")
            return

        self.event_loader = result
        parent_count = len(self.event_loader.parents_df) if self.event_loader.parents_df is not None else 0
        child_count = len(self.event_loader.children_df) if self.event_loader.children_df is not None else 0

        self.load_status_label.setText(f"✅ Parent: {parent_count:,}개, Children: {child_count:,}개")
        self.btn_search.setEnabled(True)

    # ──────────────────────────────────────────────────────
    #  A. 유사도 기반 검색
    # ──────────────────────────────────────────────────────

    def _on_search(self):
        if self.event_loader is None:
            QMessageBox.warning(self, "경고", "먼저 데이터를 로드하세요.")
            return

        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "경고", "프롬프트를 입력하세요.")
            return

        self.btn_search.setEnabled(False)
        self.btn_search.setText("검색 중...")

        try:
            result_limit = 100 if self.chk_limit_results.isChecked() else 5000

            self.search_results = self.event_loader.search_by_prompt(
                prompt=prompt,
                exclude_tags=self.exclude_input.text(),
                child_include=self.child_include_input.text() if self.child_filter_toggle.isChecked() else "",
                child_exclude=self.child_exclude_input.text() if self.child_filter_toggle.isChecked() else "",
                min_children=self.min_children_spin.value(),
                max_children=self.max_children_spin.value(),
                min_score=0,
                require_variant_set=False,
                limit=result_limit
            )

            self.result_list.clear()
            for event in self.search_results:
                summary = self.event_loader.get_event_summary(event)
                item = QListWidgetItem(summary)
                item.setData(Qt.ItemDataRole.UserRole, event)
                self.result_list.addItem(item)

            self.search_status_label.setText(f"검색 결과: {len(self.search_results)}개 (유사도순)")
            self.btn_random.setEnabled(len(self.search_results) > 0)

        except Exception as e:
            QMessageBox.critical(self, "오류", f"검색 실패:\n{e}")
            self.search_status_label.setText("❌ 검색 실패")
            import traceback
            traceback.print_exc()

        finally:
            self.btn_search.setEnabled(True)
            self.btn_search.setText("🔍 유사도 검색")

    # ──────────────────────────────────────────────────────
    #  G. 랜덤 선택
    # ──────────────────────────────────────────────────────

    def _on_random_select(self):
        if not self.search_results:
            QMessageBox.warning(self, "경고", "먼저 검색을 수행하세요.")
            return

        idx = random.randint(0, len(self.search_results) - 1)
        self.result_list.setCurrentRow(idx)
        item = self.result_list.item(idx)
        if item:
            self._on_event_selected(item)

    # ──────────────────────────────────────────────────────
    #  이벤트 선택 → 스텝 카드 표시
    # ──────────────────────────────────────────────────────

    def _on_event_selected(self, item):
        self.selected_event = item.data(Qt.ItemDataRole.UserRole)
        if not self.selected_event:
            return

        self.steps = self.event_loader.build_steps(self.selected_event)
        self._update_step_cards()

        self.btn_add_to_queue.setEnabled(True)
        self.btn_generate_now.setEnabled(True)
        self._update_total_count()
        self._update_prompt_preview()

    def _update_step_cards(self):
        self.step_cards.clear()
        # 기존 레이아웃 내용 제거
        while self.steps_flow_layout.count():
            item = self.steps_flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        cards_per_row = 4
        current_row = None
        arrow_style = f"color: {get_color('accent')}; font-size: 18px; font-weight: bold;"

        for i, step_data in enumerate(self.steps):
            col_in_row = i % cards_per_row

            if col_in_row == 0:
                # 새 행 시작
                if current_row is not None:
                    current_row.addStretch()
                current_row = QHBoxLayout()
                current_row.setSpacing(6)
                current_row.setContentsMargins(0, 0, 0, 0)
                self.steps_flow_layout.addLayout(current_row)

                # 첫 행이 아니면 이어지는 화살표 표시
                if i > 0:
                    arrow_down = QLabel("  ↳")
                    arrow_down.setStyleSheet(arrow_style)
                    current_row.addWidget(arrow_down)
            else:
                # 같은 행 안에서 화살표
                arrow = QLabel("→")
                arrow.setStyleSheet(arrow_style)
                arrow.setFixedWidth(20)
                current_row.addWidget(arrow)

            card = StepCard(step_data)
            card.carry_changed.connect(self._on_carry_changed)
            card.tags_edited.connect(self._on_tags_edited)
            self.step_cards.append(card)
            current_row.addWidget(card)

        if current_row is not None:
            current_row.addStretch()

    # ──────────────────────────────────────────────────────
    #  E. 태그 편집 반영
    # ──────────────────────────────────────────────────────

    def _on_tags_edited(self, step_index, new_tags):
        """스텝의 태그가 편집됨"""
        if 0 <= step_index < len(self.steps):
            self.steps[step_index]['tags'] = new_tags
            self.steps[step_index]['tags_str'] = ', '.join(sorted(new_tags))
        self._update_prompt_preview()

    def _on_carry_changed(self, step_index):
        """캐리 옵션 변경 시"""
        if not self.steps or not self.step_cards:
            return

        tag_classifier = None
        if self.main_window and hasattr(self.main_window, 'tag_classifier'):
            tag_classifier = self.main_window.tag_classifier

        carry_costume = set()
        carry_background = set()
        carry_appearance = set()

        for idx, step_data in enumerate(self.steps):
            if idx >= len(self.step_cards):
                break

            card = self.step_cards[idx]
            current_tags = step_data.get('tags', set())
            if isinstance(current_tags, list):
                current_tags = set(current_tags)

            carried_total = carry_costume | carry_background | carry_appearance

            if carried_total:
                carry_text = ', '.join(sorted(carried_total)[:8])
                if len(carried_total) > 8:
                    carry_text += f' ... (+{len(carried_total) - 8})'
                card.setToolTip(f"캐리된 태그 ({len(carried_total)}개):\n{carry_text}")
            else:
                card.setToolTip("")

            carry_opts = card.get_carry_options()
            all_tags = current_tags | carried_total

            if tag_classifier:
                if carry_opts['costume']:
                    for tag in all_tags:
                        classified = tag_classifier.classify_tag(tag)
                        if classified in ('clothing', 'costume'):
                            carry_costume.add(tag)
                else:
                    carry_costume.clear()

                if carry_opts['background']:
                    for tag in all_tags:
                        classified = tag_classifier.classify_tag(tag)
                        if classified == 'background':
                            carry_background.add(tag)
                else:
                    carry_background.clear()

                if carry_opts['appearance']:
                    for tag in all_tags:
                        classified = tag_classifier.classify_tag(tag)
                        if classified in ('body_parts', 'appearance', 'color', 'character_trait'):
                            carry_appearance.add(tag)
                else:
                    carry_appearance.clear()

        self._update_total_count()
        self._update_prompt_preview()

    # ──────────────────────────────────────────────────────
    #  D. 최종 프롬프트 미리보기
    # ──────────────────────────────────────────────────────

    def _update_prompt_preview(self):
        """각 스텝의 최종 프롬프트 미리보기 생성"""
        if not self.steps:
            self.prompt_preview.clear()
            return

        mw = self.main_window
        use_t2i = self.chk_use_t2i_settings.isChecked()

        prefix = ""
        suffix = ""
        artist = ""
        if use_t2i and mw:
            prefix = getattr(mw, 'prefix_prompt_text', None)
            prefix = prefix.toPlainText().strip() if prefix else ""
            suffix = getattr(mw, 'suffix_prompt_text', None)
            suffix = suffix.toPlainText().strip() if suffix else ""
            artist = getattr(mw, 'artist_input', None)
            artist = artist.text().strip() if artist else ""

        lines = []
        for i, step in enumerate(self.steps):
            tags = step.get('tags', set())
            tag_str = ', '.join(sorted(tags)) if tags else step.get('tags_str', '')

            parts = []
            if artist:
                parts.append(artist)
            if prefix:
                parts.append(prefix)
            parts.append(tag_str)
            if suffix:
                parts.append(suffix)

            final = ', '.join(parts)
            step_type = "Parent" if step.get('is_parent') else f"Child"
            lines.append(f"── Step {i} ({step_type}) ──")
            lines.append(final[:200] + ('...' if len(final) > 200 else ''))
            lines.append("")

        self.prompt_preview.setPlainText('\n'.join(lines))

    def _update_total_count(self):
        if not self.steps:
            self.total_images_label.setText("총 0장 생성 예정")
            return

        step_count = len(self.steps)
        repeat = self.repeat_spin.value()
        total = step_count * repeat
        self.total_images_label.setText(f"총 {total}장 생성 예정 ({step_count}스텝 x {repeat}반복)")

    # ──────────────────────────────────────────────────────
    #  생성 / 대기열
    # ──────────────────────────────────────────────────────

    def _on_add_to_queue(self):
        if not self.steps:
            return
        scenarios = self._build_scenarios()
        if scenarios:
            self.send_to_queue_signal.emit(scenarios)
            QMessageBox.information(self, "완료", f"{len(scenarios)}개 시나리오가 대기열에 추가되었습니다.")

    def _on_generate_now(self):
        if not self.steps:
            return
        scenarios = self._build_scenarios()
        if scenarios:
            self.send_to_queue_signal.emit(scenarios)
            if self.main_window and hasattr(self.main_window, 'start_queue_processing'):
                self.main_window.start_queue_processing()

    def _build_scenarios(self) -> list:
        if not self.steps:
            return []

        mw = self.main_window
        if not mw:
            return []

        use_t2i = self.chk_use_t2i_settings.isChecked()

        prefix_prompt = ""
        suffix_prompt = ""
        artist_prompt = ""
        negative_prompt = ""

        if use_t2i:
            prefix_prompt = mw.prefix_prompt_text.toPlainText().strip()
            suffix_prompt = mw.suffix_prompt_text.toPlainText().strip()
            artist_prompt = mw.artist_input.toPlainText().strip()
            negative_prompt = mw.neg_prompt_text.toPlainText().strip()

        try:
            steps_val = int(mw.steps_input.text())
            cfg_scale = float(mw.cfg_input.text())
            width = int(mw.width_input.text())
            height = int(mw.height_input.text())
        except Exception:
            steps_val, cfg_scale, width, height = 25, 7.0, 1024, 1024

        sampler = mw.sampler_combo.currentText()
        scheduler = mw.scheduler_combo.currentText()

        base_seed = -1
        if self.chk_fix_seed.isChecked():
            base_seed = random.randint(1, 2147483647)

        tag_classifier = getattr(mw, 'tag_classifier', None)

        scenarios = []
        repeat = self.repeat_spin.value()

        carry_costume = set()
        carry_background = set()
        carry_appearance = set()

        for step_idx, step_data in enumerate(self.steps):
            current_tags = step_data['tags'].copy()
            if isinstance(current_tags, list):
                current_tags = set(current_tags)

            current_tags.update(carry_costume)
            current_tags.update(carry_background)
            current_tags.update(carry_appearance)

            if step_idx < len(self.step_cards):
                card = self.step_cards[step_idx]
                carry_opts = card.get_carry_options()

                if carry_opts['costume']:
                    for tag in current_tags:
                        if tag_classifier and tag_classifier.classify_tag(tag) in ('clothing', 'costume'):
                            carry_costume.add(tag)
                else:
                    carry_costume.clear()

                if carry_opts['background']:
                    for tag in current_tags:
                        if tag_classifier and tag_classifier.classify_tag(tag) == 'background':
                            carry_background.add(tag)
                else:
                    carry_background.clear()

                if carry_opts['appearance']:
                    for tag in current_tags:
                        if tag_classifier and tag_classifier.classify_tag(tag) in ('body_parts', 'appearance', 'color', 'character_trait'):
                            carry_appearance.add(tag)
                else:
                    carry_appearance.clear()

            for r in range(repeat):
                prompt_parts = []
                if artist_prompt:
                    prompt_parts.append(artist_prompt)
                if prefix_prompt:
                    prompt_parts.append(prefix_prompt)
                prompt_parts.append(', '.join(sorted(current_tags)))
                if suffix_prompt:
                    prompt_parts.append(suffix_prompt)

                final_prompt = ', '.join(prompt_parts)

                payload = {
                    'prompt': final_prompt,
                    'negative_prompt': negative_prompt,
                    'steps': steps_val,
                    'cfg_scale': cfg_scale,
                    'width': width,
                    'height': height,
                    'sampler_name': sampler,
                    'scheduler': scheduler,
                    'seed': base_seed if self.chk_fix_seed.isChecked() else -1,
                    'send_images': True,
                    'save_images': True,
                    'alwayson_scripts': {},
                }

                if mw.hires_options_group.isChecked():
                    payload['enable_hr'] = True
                    payload['hr_upscaler'] = mw.upscaler_combo.currentText()
                    payload['hr_second_pass_steps'] = int(mw.hires_steps_input.text())
                    payload['denoising_strength'] = float(mw.hires_denoising_input.text())
                    payload['hr_additional_modules'] = []

                if hasattr(mw, 'negpip_group') and mw.negpip_group.isChecked():
                    payload['alwayson_scripts']['NegPiP'] = {'args': [True]}

                if mw.adetailer_group.isChecked():
                    adetailer_args = [True, False]
                    if mw.ad_slot1_group.isChecked():
                        adetailer_args.append(mw._build_adetailer_slot(mw.s1_widgets, True))
                    else:
                        adetailer_args.append(mw._build_empty_adetailer_slot())
                    if mw.ad_slot2_group.isChecked():
                        adetailer_args.append(mw._build_adetailer_slot(mw.s2_widgets, True))
                    else:
                        adetailer_args.append(mw._build_empty_adetailer_slot())
                    for _ in range(4):
                        adetailer_args.append(mw._build_empty_adetailer_slot())
                    payload['alwayson_scripts']['ADetailer'] = {'args': adetailer_args}

                is_parent = step_data.get('is_parent', False)
                step_name = "Parent" if is_parent else f"Child {step_idx}"

                scenario = {
                    'name': f"Step {step_idx} ({step_name}) [{r+1}/{repeat}]",
                    'payload': payload,
                    'step': step_idx,
                    'is_parent': is_parent,
                    'added': step_data.get('added', []),
                    'removed': step_data.get('removed', []),
                }
                scenarios.append(scenario)

        return scenarios

    # ──────────────────────────────────────────────────────
    #  설정 저장/불러오기
    # ──────────────────────────────────────────────────────

    _SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'event_gen_settings.json')

    def _save_settings(self):
        """현재 검색 설정을 파일에 저장"""
        settings = {
            'prompt': self.prompt_input.toPlainText(),
            'exclude': self.exclude_input.text(),
            'child_filter_enabled': self.child_filter_toggle.isChecked(),
            'child_include': self.child_include_input.text(),
            'child_exclude': self.child_exclude_input.text(),
            'min_children': self.min_children_spin.value(),
            'max_children': self.max_children_spin.value(),
            'limit_results': self.chk_limit_results.isChecked(),
            'ratings': {
                'g': self.chk_rating_g.isChecked(),
                's': self.chk_rating_s.isChecked(),
                'q': self.chk_rating_q.isChecked(),
                'e': self.chk_rating_e.isChecked(),
            },
            'fix_seed': self.chk_fix_seed.isChecked(),
            'use_t2i_settings': self.chk_use_t2i_settings.isChecked(),
            'repeat': self.repeat_spin.value(),
        }
        try:
            with open(self._SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "저장", "이벤트 생성 설정이 저장되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 저장 실패: {e}")

    def _load_settings(self):
        """저장된 설정을 파일에서 불러오기"""
        if not os.path.exists(self._SETTINGS_FILE):
            QMessageBox.information(self, "알림", "저장된 설정이 없습니다.")
            return
        try:
            with open(self._SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            self._apply_settings(settings)
            QMessageBox.information(self, "불러오기", "설정이 적용되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 불러오기 실패: {e}")

    def _apply_settings(self, settings: dict):
        """설정 딕셔너리를 UI에 적용"""
        self.prompt_input.setPlainText(settings.get('prompt', ''))
        self.exclude_input.setText(settings.get('exclude', ''))
        self.child_filter_toggle.setChecked(settings.get('child_filter_enabled', False))
        self.child_include_input.setText(settings.get('child_include', ''))
        self.child_exclude_input.setText(settings.get('child_exclude', ''))
        self.min_children_spin.setValue(settings.get('min_children', 2))
        self.max_children_spin.setValue(settings.get('max_children', 10))
        self.chk_limit_results.setChecked(settings.get('limit_results', True))

        ratings = settings.get('ratings', {})
        self.chk_rating_g.setChecked(ratings.get('g', False))
        self.chk_rating_s.setChecked(ratings.get('s', False))
        self.chk_rating_q.setChecked(ratings.get('q', False))
        self.chk_rating_e.setChecked(ratings.get('e', True))

        self.chk_fix_seed.setChecked(settings.get('fix_seed', True))
        self.chk_use_t2i_settings.setChecked(settings.get('use_t2i_settings', True))
        self.repeat_spin.setValue(settings.get('repeat', 1))

    def _auto_load_settings(self):
        """UI 초기화 시 자동으로 설정 불러오기"""
        if os.path.exists(self._SETTINGS_FILE):
            try:
                with open(self._SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                self._apply_settings(settings)
            except Exception:
                pass
