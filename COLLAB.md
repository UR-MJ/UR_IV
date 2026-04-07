# AI Collaboration Log

## [2026-03-27] Gemini CLI Update
- **UI Theme:** 'Gemini' 테마(Black & Yellow, Pill-style) 구현 및 `utils/theme_manager.py`에 적용.
- **Layout:** 왼쪽 패널을 NAIS2 스타일(Actions, Prompt, Character, Parameters 카드형)로 전면 개편.
- **Tabs:** 중앙 탭 이동 바를 가운데 정렬로 변경.
- **Icons:** 
  - `assets/icons/app_icon.svg` 생성 및 적용.
  - 윈도우 작업 표시줄 아이콘이 Python이 아닌 전용 앱 아이콘으로 뜨도록 `new_main_ui.py`에서 `AppUserModelID` 수정.
- **Vue Integration:** Vue UI 좌우 여백 문제 해결을 위해 `frontend/src/style.css` 리셋 및 `QWebEngineView` 테두리 제거.
- **Stability:** 각 테마(Claude, Gemini, Dark)가 독립적인 곡률(Radius)과 패딩을 갖도록 테마 시스템 구조화.

## [2026-04-07] Claude Code — Vue 전면 전환

### 구조 변경 (중요!)
- **전체 UI가 Vue SPA로 전환됨**. PyQt는 QMainWindow + QWebEngineView 껍데기만 남음.
- `_setup_ui()`가 완전 재작성됨: `self.setCentralWidget(self.vue_viewer)` — QWebEngineView 하나만.
- **모든 PyQt QWidget은 화면에 추가되지 않음** (setParent(None) 또는 더미 객체).
- 테마 시스템(GEMINI_THEME, CLAUDE_THEME 등)은 더 이상 PyQt QSS에 사용되지 않음 — Vue CSS가 대체.
  `MODERN_THEME`만 남아있고 `get_color()`는 Python 코드 호환성용으로만 사용.

### 핵심 파일
- `frontend/src/App.vue` — 전체 레이아웃 (TabBar + 좌측패널 + 콘텐츠 + 히스토리 + 대기열)
- `frontend/src/router.js` — 14개 탭 라우팅
- `frontend/src/views/*.vue` — 각 탭 컴포넌트 (14개)
- `frontend/src/components/editor/*.vue` — Editor 서브패널 (7개)
- `ui/vue_bridge.py` — Python↔Vue QWebChannel 통신
- `ui/widget_proxies.py` — PyQt 위젯 프록시 (100+개)
- `ui/generator_ui_setup.py` — _setup_ui 재작성됨

### WidgetProxy 시스템
- `self.character_input`등 모든 좌측 패널 위젯이 `WidgetProxy`로 교체됨.
- Python 백엔드(generator_settings.py, generator_prompts.py 등)는 수정 없이 동작.
- Vue `widgetStore.js`와 QWebChannel로 자동 동기화.

### 주의사항
- `utils/theme_manager.py` 수정 시: QSS 템플릿은 더 이상 PyQt에 적용되지 않음.
  Vue CSS(`frontend/src/`)에서 직접 스타일링해야 함.
- `ui/generator_ui_setup.py`의 `_create_left_panel`, `_create_center_tabs` 등은
  더 이상 호출되지 않는 데드 코드. `_setup_ui`만 사용.
- Editor 결과물은 `image_cache/editor_temp/`에 저장 (generated_images/가 아님).

## Gemini를 위한 지시사항
- Vue 파일(`frontend/src/`)을 수정할 때는 `npm run build`를 실행해야 반영됨.
- PyQt QSS/테마 변경은 더 이상 화면에 영향 없음. Vue CSS를 직접 수정해야 함.
- 새로운 Python↔Vue 통신이 필요하면 `ui/vue_bridge.py`에 `@pyqtSlot` 추가.
