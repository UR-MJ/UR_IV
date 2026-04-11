# CLAUDE.md - AI Studio Pro 개발 지침

## 프로젝트 개요
PyQt6 + Vue 3 SPA 하이브리드 AI 이미지 생성 애플리케이션.
QWebEngineView에서 Vue SPA를 렌더링하고, QWebChannel로 Python↔Vue 통신.

---

## 🏗️ 아키텍처 (v2.2.0+)

```
QMainWindow
└── QStackedWidget (_main_stack)
    ├── index 0: QWebEngineView (Vue SPA — 모든 탭)
    ├── index 1: BrowserTab (Web)
    └── index 2: BackendUITab (Backend)

Vue SPA 내부:
App.vue
├── TabBar (알약형 pill, localStorage 순서 저장)
├── main (flex)
│   ├── left-panel (T2I/I2I/Inpaint만)
│   │   ├── PromptPanel (블록 모드 지원)
│   │   └── Studio Tools (SAVE/PRESET/WEIGHT/WILDCARD/A/B TEST)
│   ├── 반달 화살표 → 확장 패널 오버레이
│   │   ├── Parameters (Resolution/Sampler/Scheduler/Steps/CFG/Seed)
│   │   ├── Hires.fix / ADetailer / NegPiP
│   │   ├── 조건부 프롬프트 → Search 탭에서 관리
│   │   └── LoRA Stack
│   ├── content (router-view + keep-alive)
│   └── right-panel (History 5개 페이지네이션 + EXIF 3탭)
├── QueuePanel (하단, 실시간 동기화)
├── VRAM 게이지 (최하단)
└── Toast 알림 시스템
```

---

## 📁 핵심 파일

### Python 백엔드
| 파일 | 역할 |
|------|------|
| `ui/vue_bridge.py` | QWebChannel 브릿지 — 모든 시그널/슬롯 (~1100줄) |
| `ui/generator_main.py` | 메인 윈도우 + _handle_vue_action (~1200줄) |
| `ui/generator_ui_setup.py` | UI 초기화 + 프록시 위젯 |
| `ui/generator_generation.py` | 이미지 생성 로직 |
| `ui/generator_prompts.py` | 프롬프트 처리 + 제외 필터 (9종 문법) |
| `ui/generator_settings.py` | 설정 저장/로드 |
| `ui/generator_actions.py` | 시그널 연결 + 액션 핸들러 |
| `ui/widget_proxies.py` | PyQt 위젯 인터페이스 프록시 |
| `core/tag_classifier.py` | tags_db 기반 태그 분류 |
| `core/ollama_client.py` | Ollama REST API 래퍼 |
| `core/sam_refiner.py` | YOLO+SAM 정밀 마스킹 |
| `core/edge_refiner.py` | 배경 제거 알파 매팅 |
| `core/error_handler.py` | 전역 에러 코드 시스템 (E001~E999) |

### Vue 프론트엔드
| 파일 | 역할 |
|------|------|
| `frontend/src/App.vue` | 전체 레이아웃 + 확장 패널 + 매니저 모달들 |
| `frontend/src/components/PromptPanel.vue` | T2I 프롬프트 입력 (블록 모드/텍스트 모드) |
| `frontend/src/components/TagBlockField.vue` | 범용 태그 블록 컴포넌트 |
| `frontend/src/components/TabBar.vue` | 알약형 탭 바 (순서 저장) |
| `frontend/src/components/CustomSelect.vue` | 커스텀 드롭다운 |
| `frontend/src/components/CompareSlider.vue` | Before/After 비교 슬라이더 |
| `frontend/src/components/QueuePanel.vue` | 대기열 (실시간 동기화) |
| `frontend/src/stores/widgetStore.js` | 위젯 상태 저장소 + useWidgetStore |
| `frontend/src/bridge.js` | QWebChannel 초기화 |

### 설정 파일
| 파일 | 역할 |
|------|------|
| `config/ui_prefs.json` | UI 설정 (블록모드, 메타데이터 패널 등) |
| `config/tab_defaults.json` | 탭별 기본값 |
| `config/cond_rules.json` | 조건부 프롬프트 규칙 |
| `config/global_weights.json` | 글로벌 태그 가중치 |
| `config/gallery_last_folder.txt` | Gallery 마지막 폴더 |
| `config/default_excludes.txt` | 기본 제외 프롬프트 (카테고리별 정리) |

---

## 🔧 개발 규칙

### 빌드
```bash
cd frontend && npm run build  # Vue 수정 후 필수
```

### 커밋
- 한글 커밋 메시지: `feat:` / `fix:` / `refactor:` / `docs:`
- 파일 수정 완료 후 commit & push

### 코딩 규칙
- **"최소한의 연결만" 같은 타협 절대 금지** — 항상 완전한 구현
- PyQt 위젯을 직접 사용하지 않음 — WidgetProxy 시스템 사용
- Vue v-model 키는 Python proxy widget_id와 동일해야 함
  (ex: `widgets.character_input` ↔ `LineEditProxy(b, 'character_input')`)
- 탭 간 이미지 전송: `tabChanged` 먼저 → 100ms 후 이미지 시그널
- 에러 발생 시 `core/error_handler.py` 사용

### Widget ID 매핑
```
Vue: widgets.character_input  ↔  Python: LineEditProxy(b, 'character_input')
Vue: widgets.model_combo      ↔  Python: ComboBoxProxy(b, 'model_combo')
Vue: widgets.total_prompt_display ↔ Python: TextEditProxy(b, 'total_prompt_display')
```

---

## 📋 제외 프롬프트 문법 (9종)

| 제외 | 예외 |
|------|------|
| `단어` 포함 제외 | `~단어` 완전일치 유지 |
| `*단어` 완전일치 제외 | `~_단어` 접미 유지 |
| `_단어` 접미 제외 | `~단어_` 접두 유지 |
| `단어_` 접두 제외 | `~_단어_` 포함 유지 |
| `_단어_` 포함 제외 | |

---

## 🔑 주요 시그널 (Python → Vue)

```
imageGenerated, generationStarted, generationError, generationProgress
editorImageLoaded, i2iImageLoaded, inpaintImageLoaded
widgetValueChanged, widgetPropertyChanged, batchUpdate
searchResultsReady, eventSearchResults, searchStatus
loraInserted, yoloModelUpdated, compareImageLoaded
vramUpdated, ollamaResult, condRulesLoaded
queueUpdated, queueItemAdded, queueCompleted
showNotification, uiPrefsLoaded, globalWeightsLoaded
batchFilesSelected, seedExploreResult, tabChanged
```

---

## 🤖 Gemini CLI 활용
```bash
gemini chat "질문" --no-stream
gemini chat "@파일경로 분석해줘" --no-stream
```

---

## 📦 의존성
```
PyQt6, PyQt6-WebEngine, requests, pandas, pyarrow, Pillow,
opencv-python, numpy, exifread, websocket-client, send2trash,
ultralytics, timm, rembg, pymatting
# MobileSAM: pip install git+https://github.com/ChaoningZhang/MobileSAM.git
```
