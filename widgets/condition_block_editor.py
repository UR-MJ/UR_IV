# widgets/condition_block_editor.py
"""블록 기반 조건부 프롬프트 에디터 위젯"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QScrollArea, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from utils.condition_block import ConditionRule, rules_to_json, rules_from_json, migrate_old_rules


_LABEL_STYLE = "color: #888; font-size: 11px; font-weight: bold;"
_INPUT_STYLE = (
    "QLineEdit { background-color: #2A2A2A; color: #DDD; "
    "border: 1px solid #444; border-radius: 4px; padding: 2px 6px; font-size: 11px; }"
    "QLineEdit:focus { border: 1px solid #5865F2; }"
)
# 드롭다운 팝업 항목 스타일 (다크모드 대응)
_COMBO_POPUP = (
    "QComboBox QAbstractItemView { background-color: #2A2A2A; color: #DDD; "
    "selection-background-color: #3A3A5A; selection-color: #FFF; "
    "border: 1px solid #555; }"
)
_COMBO_STYLE = (
    "QComboBox { background-color: #2A2A2A; color: #DDD; "
    "border: 1px solid #444; border-radius: 4px; padding: 2px 4px; font-size: 11px; }"
    "QComboBox::drop-down { border: none; }"
    "QComboBox::down-arrow { image: none; border: none; width: 8px; }" + _COMBO_POPUP
)
_TARGET_POS_STYLE = (
    "QComboBox { background-color: #1A3A1A; color: #4CAF50; "
    "border: 1px solid #4CAF50; border-radius: 4px; padding: 2px 4px; "
    "font-size: 11px; font-weight: bold; }"
    "QComboBox::drop-down { border: none; }"
    "QComboBox::down-arrow { image: none; border: none; width: 8px; }" + _COMBO_POPUP
)
_TARGET_NEG_STYLE = (
    "QComboBox { background-color: #3A1A1A; color: #F44336; "
    "border: 1px solid #F44336; border-radius: 4px; padding: 2px 4px; "
    "font-size: 11px; font-weight: bold; }"
    "QComboBox::drop-down { border: none; }"
    "QComboBox::down-arrow { image: none; border: none; width: 8px; }" + _COMBO_POPUP
)


class ConditionBlockRow(QFrame):
    """단일 조건부 규칙 블록"""

    removed = pyqtSignal(object)  # self
    changed = pyqtSignal()

    EXIST_OPTIONS = ["있다", "없다"]
    TARGET_OPTIONS = ["Positive", "Negative"]
    LOCATION_OPTIONS = ["main", "prefix", "suffix", "조건 뒤에", "랜덤"]
    LOCATION_MAP = {
        "main": "main", "prefix": "prefix", "suffix": "suffix",
        "조건 뒤에": "after_condition", "랜덤": "random",
    }
    LOCATION_REVERSE = {v: k for k, v in LOCATION_MAP.items()}
    ACTION_OPTIONS = ["추가한다", "제거한다", "대체한다"]
    ACTION_MAP = {"추가한다": "add", "제거한다": "remove", "대체한다": "replace"}
    ACTION_REVERSE = {v: k for k, v in ACTION_MAP.items()}

    def __init__(self, rule: ConditionRule = None, parent=None):
        super().__init__(parent)
        self._rule = rule or ConditionRule()
        self._init_ui()
        self._load_from_rule()

    def _init_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "ConditionBlockRow { background-color: #252525; "
            "border: 1px solid #3A3A3A; border-radius: 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 1줄: [활성화] [만약] [조건태그] [이/가] [있다/없다]
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._chk_enabled = QCheckBox()
        self._chk_enabled.setChecked(True)
        self._chk_enabled.setFixedSize(18, 18)
        self._chk_enabled.toggled.connect(self._on_changed)
        row1.addWidget(self._chk_enabled)

        lbl_if = QLabel("만약")
        lbl_if.setStyleSheet("color: #5865F2; font-weight: bold; font-size: 11px;")
        lbl_if.setFixedWidth(28)
        row1.addWidget(lbl_if)

        self._input_condition = QLineEdit()
        self._input_condition.setPlaceholderText("조건 태그")
        self._input_condition.setStyleSheet(_INPUT_STYLE)
        self._input_condition.setMaximumWidth(160)
        self._input_condition.setMinimumWidth(80)
        self._input_condition.textChanged.connect(self._on_changed)
        row1.addWidget(self._input_condition)

        lbl_particle = QLabel("이/가")
        lbl_particle.setStyleSheet(_LABEL_STYLE)
        lbl_particle.setFixedWidth(28)
        row1.addWidget(lbl_particle)

        self._combo_exists = QComboBox()
        self._combo_exists.addItems(self.EXIST_OPTIONS)
        self._combo_exists.setStyleSheet(_COMBO_STYLE)
        self._combo_exists.setFixedWidth(55)
        self._combo_exists.currentIndexChanged.connect(self._on_changed)
        row1.addWidget(self._combo_exists)

        layout.addLayout(row1)

        # 2줄: [대상태그] 를 [Positive/Negative] [위치] 에 [동작] [삭제]
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        # 들여쓰기
        spacer = QLabel("")
        spacer.setFixedWidth(22)
        row2.addWidget(spacer)

        self._input_tags = QLineEdit()
        self._input_tags.setPlaceholderText("대상 태그 (쉼표 구분)")
        self._input_tags.setStyleSheet(_INPUT_STYLE)
        self._input_tags.setMaximumWidth(200)
        self._input_tags.setMinimumWidth(100)
        self._input_tags.textChanged.connect(self._on_changed)
        row2.addWidget(self._input_tags)

        lbl_to = QLabel("를")
        lbl_to.setStyleSheet(_LABEL_STYLE)
        lbl_to.setFixedWidth(14)
        row2.addWidget(lbl_to)

        # 적용 대상: Positive / Negative
        self._combo_target = QComboBox()
        self._combo_target.addItems(self.TARGET_OPTIONS)
        self._combo_target.setStyleSheet(_TARGET_POS_STYLE)
        self._combo_target.setFixedWidth(80)
        self._combo_target.currentIndexChanged.connect(self._on_target_changed)
        row2.addWidget(self._combo_target)

        # 위치 (Positive일 때만 의미 있음)
        self._combo_location = QComboBox()
        self._combo_location.addItems(self.LOCATION_OPTIONS)
        self._combo_location.setStyleSheet(_COMBO_STYLE)
        self._combo_location.setFixedWidth(80)
        self._combo_location.currentIndexChanged.connect(self._on_changed)
        row2.addWidget(self._combo_location)

        lbl_at = QLabel("에")
        lbl_at.setStyleSheet(_LABEL_STYLE)
        lbl_at.setFixedWidth(12)
        row2.addWidget(lbl_at)

        self._combo_action = QComboBox()
        self._combo_action.addItems(self.ACTION_OPTIONS)
        self._combo_action.setStyleSheet(_COMBO_STYLE)
        self._combo_action.setFixedWidth(72)
        self._combo_action.currentIndexChanged.connect(self._on_changed)
        row2.addWidget(self._combo_action)

        btn_del = QPushButton("X")
        btn_del.setFixedSize(24, 24)
        btn_del.setStyleSheet(
            "QPushButton { background-color: #C0392B; color: white; "
            "border-radius: 4px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background-color: #E74C3C; }"
        )
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        row2.addWidget(btn_del)

        layout.addLayout(row2)

    def _on_target_changed(self, index: int):
        """적용 대상 변경 시 위치 콤보 활성화/비활성화 + 스타일"""
        is_negative = (index == 1)
        self._combo_location.setEnabled(not is_negative)
        self._combo_location.setVisible(not is_negative)
        self._combo_target.setStyleSheet(
            _TARGET_NEG_STYLE if is_negative else _TARGET_POS_STYLE
        )
        self._on_changed()

    def _load_from_rule(self):
        """ConditionRule -> UI"""
        self._chk_enabled.setChecked(self._rule.enabled)
        self._input_condition.setText(self._rule.condition_tag)
        self._combo_exists.setCurrentIndex(0 if self._rule.condition_exists else 1)
        self._input_tags.setText(", ".join(self._rule.target_tags))

        # 타겟 & 위치 설정
        if self._rule.location == "neg":
            self._combo_target.setCurrentIndex(1)  # Negative
        else:
            self._combo_target.setCurrentIndex(0)  # Positive
            loc_display = self.LOCATION_REVERSE.get(self._rule.location, "main")
            idx = self.LOCATION_OPTIONS.index(loc_display) if loc_display in self.LOCATION_OPTIONS else 0
            self._combo_location.setCurrentIndex(idx)

        act_display = self.ACTION_REVERSE.get(self._rule.action, "추가한다")
        idx = self.ACTION_OPTIONS.index(act_display) if act_display in self.ACTION_OPTIONS else 0
        self._combo_action.setCurrentIndex(idx)

    def to_rule(self) -> ConditionRule:
        """UI -> ConditionRule"""
        tags_text = self._input_tags.text()
        tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        act_text = self._combo_action.currentText()

        # 타겟에 따라 위치 결정
        is_negative = (self._combo_target.currentIndex() == 1)
        if is_negative:
            location = "neg"
        else:
            loc_text = self._combo_location.currentText()
            location = self.LOCATION_MAP.get(loc_text, "main")

        return ConditionRule(
            condition_tag=self._input_condition.text().strip(),
            condition_exists=(self._combo_exists.currentIndex() == 0),
            target_tags=tags,
            location=location,
            action=self.ACTION_MAP.get(act_text, "add"),
            enabled=self._chk_enabled.isChecked(),
        )

    def _on_changed(self):
        self.changed.emit()


class ConditionBlockEditor(QWidget):
    """블록 기반 조건부 프롬프트 에디터"""

    rules_changed = pyqtSignal()  # 규칙 변경 시

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: list[ConditionBlockRow] = []
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # 스크롤 영역
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._scroll_container = QWidget()
        self._scroll_container.setStyleSheet("background: transparent;")
        self._blocks_layout = QVBoxLayout(self._scroll_container)
        self._blocks_layout.setContentsMargins(0, 0, 0, 0)
        self._blocks_layout.setSpacing(4)
        self._blocks_layout.addStretch()
        self._scroll.setWidget(self._scroll_container)
        root.addWidget(self._scroll, 1)

        # + 규칙 추가 버튼
        btn_add = QPushButton("+ 규칙 추가")
        btn_add.setFixedHeight(30)
        btn_add.setStyleSheet(
            "QPushButton { background-color: #333; color: #AAA; "
            "border: 1px dashed #555; border-radius: 6px; "
            "font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #444; color: #DDD; }"
        )
        btn_add.clicked.connect(lambda: self.add_rule(ConditionRule()))
        root.addWidget(btn_add)

    def add_rule(self, rule: ConditionRule):
        """규칙 블록 추가"""
        block = ConditionBlockRow(rule)
        block.removed.connect(self._on_block_removed)
        block.changed.connect(self._on_block_changed)
        self._blocks.append(block)
        # stretch 앞에 삽입
        self._blocks_layout.insertWidget(self._blocks_layout.count() - 1, block)
        self.rules_changed.emit()

    def _on_block_removed(self, block: ConditionBlockRow):
        """블록 삭제"""
        if block in self._blocks:
            self._blocks.remove(block)
        self._blocks_layout.removeWidget(block)
        block.deleteLater()
        self.rules_changed.emit()

    def _on_block_changed(self):
        self.rules_changed.emit()

    def get_rules(self) -> list[ConditionRule]:
        """현재 모든 규칙 반환"""
        return [b.to_rule() for b in self._blocks]

    def get_rules_json(self) -> str:
        """규칙을 JSON 문자열로 반환"""
        return rules_to_json(self.get_rules())

    def set_rules(self, rules: list[ConditionRule]):
        """규칙 리스트로 에디터 세팅"""
        self.clear()
        for rule in rules:
            self.add_rule(rule)

    def set_rules_json(self, text: str):
        """JSON 문자열로 에디터 세팅"""
        rules = rules_from_json(text)
        self.set_rules(rules)

    def load_from_text(self, text: str):
        """기존 텍스트 문법 또는 JSON에서 로드 (자동 감지)"""
        if not text or not text.strip():
            self.clear()
            return
        stripped = text.strip()
        if stripped.startswith("["):
            rules = rules_from_json(text)
        else:
            rules = migrate_old_rules(text)
        self.set_rules(rules)

    def clear(self):
        """모든 블록 제거"""
        for block in self._blocks[:]:
            self._blocks_layout.removeWidget(block)
            block.deleteLater()
        self._blocks.clear()

    def rule_count(self) -> int:
        return len(self._blocks)
