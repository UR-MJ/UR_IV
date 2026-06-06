# UR_IV — Claude Code 작업 가이드

PyQt6(백엔드) + Vue 3 SPA(프론트) 데스크탑 AI 이미지 생성기. (내부명 AI Studio Pro)

## ⚠️ 작업 전 필수 (이걸 안 지켜서 실수 많았음)
- **모든 git / npm build 는 메인 repo `C:\Users\KMJ\Desktop\Image viewer` 에서** 한다.
  `.claude/worktrees/...` 경로에서 빌드/커밋하면 변경이 유실되거나 dist가 안 맞는다.
- **Vue(`frontend/src/`) 수정 후엔 반드시 `cd frontend && npm run build`** — dist를 안 만들면
  앱은 옛 화면을 보여준다. `frontend_dist`도 같이 커밋.
- **Python 수정 후엔 `python run_tests.py`** 로 회귀 검증. (자동 훅으로도 돈다.)
- API 키/시크릿/토큰은 절대 커밋 금지. 노출되면 재발급 안내.

## 검증 / 배포
- `/verify` — 테스트 + py_compile + (프론트 수정 시) 빌드. **커밋 안 함**.
- `/ship` — 검증 → 빌드 → 커밋(한국어 conventional) → 푸시.
- 수동: `python run_tests.py` (pytest 불필요, 표준 unittest).

## 아키텍처
- 프론트: Vue 3 SPA in QWebEngineView — `frontend/src/`
- 백엔드: PyQt6 (QMainWindow + QWebChannel) — `ui/`, `core/`, `backends/`
- 브리지: `ui/vue_bridge.py`(Python @pyqtSlot/Signal) ↔ `frontend/src/bridge.js`
- 위젯 프록시: `ui/widget_proxies.py` — Vue `storeWidgets.<id>` ↔ 프록시 widget_id
- 상태 저장소: `frontend/src/stores/widgetStore.js`

## 브리지 계약 (불일치 = 버그 주원인)
- 액션: Vue `requestAction(name, payload)` / `action(name)` → `generator_main._handle_vue_action`
  의 `action == 'name'` 또는 `action in ('a','b')`
- 이벤트: Python `vue_bridge.<signal>.emit(json)` → Vue `onBackendEvent(name, cb)`
- 페이로드 형태를 양쪽이 똑같이 맞춰야 함 (예전 버그: 조건식 `target`(문자열) vs `tags`(리스트))
- **회귀 가드**: `tests/test_bridge_contract.py` — 프론트 액션/이벤트 이름이 Python
  핸들러/시그널과 매칭되는지 정적 검증. 새 액션 추가 시 핸들러 빠지면 테스트가 잡음.

## 프론트 타입 (점진 TS 도입 ②)
- 툴: `typescript` + `vue-tsc` 설치됨. `frontend/tsconfig.json`(allowJs, checkJs:false —
  기존 .js는 느슨, 새 .ts/lang="ts"만 엄격). **Vite 빌드는 esbuild라 타입검사 안 함** → 타입검사는
  `cd frontend && npm run type-check`(= `vue-tsc --noEmit`). **현재 0 errors가 베이스라인**.
- `frontend/src/types/bridge.d.ts` — 브리지 계약 타입(`ActionName`/`BackendEvent` + 페이로드).
  `requestAction`/`onBackendEvent`에 JSDoc 연결 → 에디터 자동완성. 이름 정합성 **강제는
  `tests/test_bridge_contract.py`**(.d.ts는 편의용, `(string&{})`라 드리프트 무해).
- **점진 전환**: 컴포넌트마다 `<script setup lang="ts">` + 타입 기반 props/emits로 전환,
  전환 후 `npm run type-check`(0 유지) + 런타임 스모크. 첫 예시: `components/ToggleSwitch.vue`
  (`withDefaults(defineProps<{...}>(), {...})` 패턴). 한 번에 갈아엎지 말 것.

## 커밋 규칙
- 한국어 conventional: feat/fix/refactor/test/chore/docs
- 메시지 끝에 `Co-Authored-By: Claude ...` 트레일러
- 런타임 데이터 커밋 금지: `config/cond_rules.json`, `config/char_global_prefs.json`,
  `config/session_backup.json` (gitignore 처리됨)

## 테스트
- `tests/` (표준 unittest), 실행 `python run_tests.py`
- 순수 로직은 Qt에서 분리해 테스트 추가 (예: `core/resolution_guard.py`)
- 커버: 조건식 / 캐릭터 분류 / NL 누출제거 / ANIMA 해상도캡
