import sys
import re
import random
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QFrame, QSplitter, QCheckBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

class RuleSimulatorApp(QWidget):
    def __init__(self):
        super().__init__()
        # [수정됨] 정규표현식 단순화: (조건):/위치+=태그들
        # ift/ifn 제거됨
        self.rule_regex = re.compile(r"^\s*\((.+?)\)\s*:\s*/?\s*([crpfl]|\[.+?\])\s*\+=\s*(.+?)\s*$")
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("조건식 시뮬레이터 (v2.0)")
        self.setGeometry(200, 200, 700, 650)

        main_layout = QVBoxLayout(self)
        
        # 상단(입력)과 하단(결과)을 분리하는 스플리터 생성
        main_splitter = QSplitter(Qt.Vertical)
        
        # --- 상단 입력 패널 ---
        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(15, 15, 15, 15)
        top_layout.setSpacing(10)

        # 1. 테스트 프롬프트 입력
        prompt_label = QLabel("1. 테스트할 프롬프트를 입력하세요 (쉼표로 구분)")
        prompt_label.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        top_layout.addWidget(prompt_label)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("예: 1girl, hakurei reimu, black hair, dress")
        self.prompt_input.setFixedHeight(80)
        top_layout.addWidget(self.prompt_input)

        # 2. 조건식 입력
        rule_label = QLabel("2. 실행할 조건식을 입력하세요")
        rule_label.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        top_layout.addWidget(rule_label)

        self.rule_input = QLineEdit()
        self.rule_input.setPlaceholderText("(hakurei reimu):/c+=touhou, zun style")
        self.rule_input.setFont(QFont("Consolas", 10))
        top_layout.addWidget(self.rule_input)
        
        # [추가됨] 중복 방지 체크박스
        self.dupe_check = QCheckBox("중복 태그 방지 (이미 존재하는 태그는 추가 안 함)")
        self.dupe_check.setChecked(True) # 기본값 ON
        self.dupe_check.setStyleSheet("color: #FFD700; font-weight: bold;")
        top_layout.addWidget(self.dupe_check)

        # 3. 실행 버튼
        self.simulate_button = QPushButton("조건식 실행 (Simulate)")
        self.simulate_button.setFixedHeight(40)
        self.simulate_button.clicked.connect(self.on_simulate_click)
        top_layout.addWidget(self.simulate_button)

        # --- 하단 결과 패널 ---
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(15, 15, 15, 15)
        bottom_layout.setSpacing(10)

        result_label = QLabel("실행 결과")
        result_label.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        bottom_layout.addWidget(result_label)

        self.result_output = QTextEdit()
        self.result_output.setReadOnly(True)
        bottom_layout.addWidget(self.result_output)

        main_splitter.addWidget(top_panel)
        main_splitter.addWidget(bottom_panel)
        main_splitter.setStretchFactor(1, 1) 
        
        main_layout.addWidget(main_splitter)
        self.setLayout(main_layout)

    def on_simulate_click(self):
        """'조건식 실행' 버튼 클릭 시 실행되는 메인 로직"""
        base_prompt_str = self.prompt_input.toPlainText()
        rule_str = self.rule_input.text()

        if not base_prompt_str or not rule_str:
            self.result_output.setText("<font color='orange'>프롬프트와 조건식을 모두 입력해주세요.</font>")
            return
        
        # 시뮬레이션 실행
        simulation_result_html = self.run_simulation(rule_str, base_prompt_str)
        
        # 문법 해석 추가
        interpretation_html = self.interpret_rule(rule_str)

        # 최종 결과 조합
        final_html = simulation_result_html + "<hr>" + interpretation_html
        self.result_output.setHtml(final_html)

    def _check_condition(self, condition_str, tags_set):
        """AND/OR 조건을 검사하는 헬퍼 함수"""
        condition_str = condition_str.strip()
        if '&' in condition_str:
            return all(tag.strip() in tags_set for tag in condition_str.split('&'))
        elif '|' in condition_str:
            return any(tag.strip() in tags_set for tag in condition_str.split('|'))
        else:
            return condition_str in tags_set

    def run_simulation(self, rule_str, base_prompt_str):
        """조건식을 실제 프롬프트에 적용하고 결과를 HTML로 반환"""
        # 입력 준비
        prompt_parts = [tag.strip() for tag in base_prompt_str.split(',') if tag.strip()]
        current_tags_set = set(prompt_parts)
        
        match = self.rule_regex.match(rule_str.strip())
        if not match:
            return "<h3>시뮬레이션 결과: <font color='red'>실패</font></h3><p>규칙이 문법에 맞지 않습니다.</p>"

        # 그룹 파싱 (ift/ifn 제거됨)
        condition_str, position, tags_to_add_str = match.groups()

        # 1. 조건 검사
        if not self._check_condition(condition_str, current_tags_set):
            return f"<h3>시뮬레이션 결과: <font color='orange'>실행 안됨</font></h3><p><b>이유:</b> 발동 조건 <code>({condition_str})</code>이(가) 충족되지 않았습니다.</p>"

        # 2. 추가할 태그 목록 생성 (단순 쉼표 분리)
        tags_to_add = [tag.strip() for tag in tags_to_add_str.split(',') if tag.strip()]

        # [수정됨] 중복 방지 로직 (체크박스 기반)
        skipped_tags = []
        if self.dupe_check.isChecked():
            filtered_tags = []
            for tag in tags_to_add:
                if tag in current_tags_set:
                    skipped_tags.append(tag)
                else:
                    filtered_tags.append(tag)
            tags_to_add = filtered_tags
        
        if not tags_to_add:
            msg = "추가할 태그가 없습니다."
            if skipped_tags:
                msg = f"추가하려던 태그(<code>{', '.join(skipped_tags)}</code>)가 이미 존재하여 중복 방지되었습니다."
            return f"<h3>시뮬레이션 결과: <font color='orange'>실행 안됨</font></h3><p><b>이유:</b> {msg}</p>"

        # 3. 위치에 따라 프롬프트 수정
        final_prompt_parts = list(prompt_parts)
        
        if position == 'c' or position == 'pf':
            final_prompt_parts = tags_to_add + final_prompt_parts
        elif position == 'r':
            for tag in reversed(tags_to_add):
                insert_pos = random.randint(0, len(final_prompt_parts))
                final_prompt_parts.insert(insert_pos, tag)
        elif position == 'lf':
            final_prompt_parts.extend(tags_to_add)
        elif position.startswith('[') and position.endswith(']'):
            keyword = position[1:-1]
            try:
                idx = final_prompt_parts.index(keyword)
                for i, tag in enumerate(tags_to_add):
                    final_prompt_parts.insert(idx + 1 + i, tag)
            except ValueError:
                # 키워드가 없으면 맨 뒤에 추가 (메인 로직과 동일하게)
                final_prompt_parts.extend(tags_to_add)
        
        # 4. 최종 결과 HTML 생성
        skipped_msg = ""
        if skipped_tags:
            skipped_msg = f"<br>(중복 방지됨: <font color='gray'>{', '.join(skipped_tags)}</font>)"

        result_html = f"""
        <h3>시뮬레이션 결과: <font color='lime'>성공</font></h3>
        <p><b>추가된 태그:</b> <font color='cyan'>{'<b>, </b>'.join(f'<code>{t}</code>' for t in tags_to_add)}</font>{skipped_msg}</p>
        <p><b>변경 전:</b><br>{', '.join(prompt_parts)}</p>
        <p><b>변경 후:</b><br>{', '.join(final_prompt_parts)}</p>
        """
        return result_html

    def interpret_rule(self, rule_str):
        """변경된 문법에 맞춘 규칙 해석"""
        match = self.rule_regex.match(rule_str.strip())
        if not match: return "<h3>규칙 분석</h3><p><font color='red'><b>오류:</b> 문법이 올바르지 않습니다.</font></p>"
        
        condition_str, position, tags_to_add_str = match.groups()
        
        parts = ["<h3>규칙 분석</h3>"]
        
        # 조건 분석
        cond_text = "<b>1. 발동 조건:</b> "
        if '&' in condition_str: tags = [f"<code>{t.strip()}</code>" for t in condition_str.split('&')]; cond_text += f"{', '.join(tags)} 태그가 <b>모두</b> 존재할 때"
        elif '|' in condition_str: tags = [f"<code>{t.strip()}</code>" for t in condition_str.split('|')]; cond_text += f"{', '.join(tags)} 태그 중 <b>하나 이상</b> 존재할 때"
        else: cond_text += f"<code>{condition_str.strip()}</code> 태그가 존재할 때"
        parts.append(cond_text)

        # 위치 분석
        pos_map = {'c': "캐릭터 태그 바로 뒤", 'pf': "선행 프롬프트 바로 뒤", 'r': "메인 프롬프트 내 임의 위치", 'lf': "후행 프롬프트 바로 앞"}
        pos_text = f"<b>2. 추가 위치:</b> <code>{position}</code>"
        if position in pos_map: pos_text += f" → {pos_map[position]}"
        elif position.startswith('[') and position.endswith(']'): pos_text += f" → <code>{position[1:-1]}</code> 태그 바로 뒤"
        parts.append(pos_text)

        # 동작 분석 (중복 방지 여부 포함)
        action_text = "<b>3. 실행 동작:</b> "
        tags = [f"<code>{t.strip()}</code>" for t in tags_to_add_str.split(',')]
        action_text += f"{', '.join(tags)} 태그를 추가함."
        
        if self.dupe_check.isChecked():
            action_text += " <font color='orange'>(중복 방지 켜짐: 이미 있는 태그는 건너뜀)</font>"
        else:
            action_text += " (중복 방지 꺼짐: 무조건 추가함)"
        parts.append(action_text)

        return "<br><br>".join(parts)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # 스타일시트는 기존과 동일한 다크 테마
    app.setStyleSheet("""
        QWidget { background-color: #2E2E2E; color: #E0E0E0; font-family: 'Malgun Gothic'; }
        QTextEdit, QLineEdit { background-color: #3C3C3C; border: 1px solid #505050; border-radius: 4px; padding: 5px; }
        QPushButton { background-color: #4A90E2; color: white; border: none; border-radius: 4px; padding: 8px; font-weight: bold; }
        QPushButton:hover { background-color: #6DC5FF; }
        QSplitter::handle { background-color: #4F4F4F; }
        QSplitter::handle:vertical { height: 4px; }
        code { background-color: #4F4F4F; color: #A5D6FF; padding: 2px 4px; border-radius: 3px; font-family: 'Consolas'; }
        QCheckBox { color: #E0E0E0; spacing: 5px; }
        QCheckBox::indicator { width: 15px; height: 15px; }
    """)
    simulator = RuleSimulatorApp()
    simulator.show()
    sys.exit(app.exec_())