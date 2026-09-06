# UI 품질 수정 및 검증 · 2026-09-05

로컬 체크아웃에 적용하고 `frontend_dist`를 다시 빌드했다. 실행 중인 앱은 완전히 종료 후 다시 실행해야 Python 변경까지 반영된다. 커밋·푸시·백엔드 재시작·모델 다운로드는 하지 않았다.

## 요청별 결과

| 항목 | 적용 내용 |
| --- | --- |
| 다운로드 카드 글자 넘침 | 체크박스 label의 강제 줄바꿈 금지와 grid 최소 너비 문제 수정. 11개 기능의 실제 문구로 확인. |
| 폴더 찾아보기 | 기존 설치/확장/모델 경로를 유지하며 부모 창이 명확한 Qt 폴더 선택창 사용. 선택 중·취소·선택 완료 피드백 추가. 연결/저장 전에는 설정을 바꾸지 않음. |
| Web·Backend 라이트 모드 | 검정 배경의 자식 위젯 상속 제거. 상단바와 웹 확인창에 현재 테마 적용, 테마 전환 시 즉시 갱신. |
| 아이콘 hover 반복 | GPT와 Claude 모두 기존 의미별 모션을 반복. press 중 반복 중지, 이탈 시 복귀, 없음 기본값 유지. Claude의 아이콘 모양·콘셉트는 변경하지 않음. |
| 대화 복사 | 앱에서는 확인 가능한 네이티브 클립보드 경로 사용. 웹은 접속한 단말의 클립보드 사용. 실패를 성공으로 표시하지 않음. |
| PNG Info 분리 복사 | Prompt만·Negative만 복사 버튼, 원본 Comfy JSON 별도 보기/복사. |
| ComfyUI 메타데이터 | Gallery·PNG Info·히스토리에서 동일 파서 사용. 연결을 따라 문장/설정 추출, 모호하면 자동 적용 차단, 원본 보존. |
| 설정 하위 검색 | `중복 자동 정리`처럼 항목 문구로 검색하여 탭과 해당 항목으로 이동·강조. 입력값이나 비밀키를 검색 인덱스로 읽지 않음. |
| XYZ 축 | Forge API 스키마/목록 및 Comfy object_info에서 앱이 실제 적용할 수 있는 축과 값을 조회. 미지원 확장 축은 별도로 안내. |
| XYZ 실행 보존 | 모델·LoRA·확장·기본 설정 스냅샷 유지. 수동 생성 중 시작 거절. 제출 전 백엔드 변경/점유는 큐를 버리지 않고 일시정지. |
| 하단 모델 목록 | 화면의 위/아래 공간을 보고 방향 결정, 스크롤/크기 변경 대응, 메뉴가 다른 컨테이너에 잘리지 않음. |
| VRAM | 1초 간격으로 조회하되 느린 조회가 겹쳐 쌓이지 않도록 보호. |
| 대화 설정 | 실제 모델 메타데이터의 MoE·추론 지원 표시 및 온도 설명. MoE는 모델 구조 자체로 자동 사용되며 Dense를 MoE로 바꾸는 가짜 옵션은 없음. |
| 개선 지침 | 대화 설정 → 지침 프리셋 → **개선 · 태그와 자연어 캡션** → 선택한 지침 적용. 개인 지침 백업/복원. 태그→영어 자연어 2문장 이상→한국어 설명 순서, 인물 수는 마지막 설명에만 작성. |

추가로 대화 삭제 확인창의 대비·중앙 정렬·취소 포커스, 늦게 도착한 모델 정보의 오류 표시, 완료 신호 없이 끊긴 답변의 오류 처리도 보강했다. 부분 답변은 보존한다.

## 주요 수정 파일

- 화면: `frontend/src/views/{SettingsView,ChatView,GalleryView,PngInfoView,XYZPlotView}.vue`
- 공통 UI: `frontend/src/components/{CustomSelect,ModelDownloadsSettings,ComfyMetadataDetails}.vue`
- 동작: `frontend/src/utils/{clipboard,chatSettings,dropdownPlacement,settingsSearch,xyzPlot}.ts`
- 모션: `frontend/src/styles/{iconMotion,iconMotionClaude}.css`
- 네이티브 화면: `tabs/{browser_tab,backend_ui_tab}.py`, `ui/{native_dialogs,studio_qwebchannel,generator_ui_setup}.py`
- 브리지·생성: `ui/{vue_bridge,generator_main,generator_generation,xyz_actions,chat_actions}.py`, `workers/{generation_worker,chat_worker}.py`, `web_main_ui.py`, `frontend/src/types/bridge.d.ts`
- 해석·기능 조회: `core/{image_metadata,comfy_metadata,xyz_capabilities,ollama_client}.py`
- 테스트: 해당 Python/프론트 회귀 테스트, 기존 Vue 플러그인을 사용하는 `frontend/vitest.config.js`. 의존성 추가 없음.
- 개발 전용 화면: `frontend/dev/creator-integration.html` 및 `.js`. 오프라인 테스트 데이터만 사용하며 제품 빌드에는 포함되지 않는다.

## 모션 수치

- GPT hover 한 주기 1,000ms, `cubic-bezier(.4, 0, .2, 1)`. 처음 약 200ms 동안 반응하고 복귀·짧은 휴지 구간을 포함.
- Claude 기본 hover 반복 1,100ms, 기존 `--ic-ease` 사용. 기존 단발 키프레임 일부는 1,400ms 주기로 반복하며 기존 전용 반복 효과는 유지.
- 기존 press와 상태 전환 수치는 유지. press에는 hover 애니메이션을 겹치지 않는다.
- 두 스타일 모두 `(hover: hover) and (pointer: fine)`에서만 hover 반복. `prefers-reduced-motion: reduce`에서는 이동·회전·확대·반복을 제거하고 색/불투명도 피드백만 유지.

## 검증 결과

- Python 전체: **1,272개 실행, 1,269개 통과, 3개 건너뜀, 실패 0**.
- 건너뜀: 별도 Cosmos 통합 환경 미설정, PyAV 미설치 전용 분기, Windows 디렉터리 심볼릭 링크 권한 조건.
- 프론트: **19개 테스트 파일 / 128개 테스트 통과**.
- 변경·추가 Python **57개 문법 검사 통과**. 마지막 축 필드 수정도 재검사.
- `npm run type-check`, `npm run build`, 저장소의 기존 줄바꿈 정책에 따른 `git diff --check` 통과. 별도 lint 명령은 프로젝트에 없음.
- 브라우저: 1280×720 및 390×844 카드 넘침 없음. 하단 메뉴가 위쪽으로 열려 모든 모델을 선택할 수 있음. 검색 이동, 대화/Prompt/Negative 복사 요청, MoE 표시, XYZ 값 목록·조합 제출, 라이트/다크 확인창 검증.
- 모션: GPT/Claude hover 유지 중 반복, 빠른 재진입 및 연속 클릭에서 press 충돌 없음, 이탈 후 transform 복귀와 버튼 영역 유지 확인. 없음 선택에서 반복 없음.
- 소프트웨어 Qt: 기존 설치 경로에서 폴더 선택/취소, 부모 창, 라이트/다크/실시간 테마 전환 검증. 원래 검정 바 대비 약 1.13:1인 재현을 수정 후 4.5:1 이상으로 확인.
- 메타데이터: 임시 PNG/JPEG/WebP로 실제 파서와 액션을 검증. 원본 이미지 바이트 보존. XYZ는 실제 큐/워커/컴파일러에 가짜 백엔드를 연결하여 설정 반영·작업 보존 검증.
- 개인 `config/gallery_last_folder.txt`는 시작 시 SHA-256과 동일함을 확인.

## 남아 있는 확인 범위

- 실제 GPU 생성·LLM 추론·모델 다운로드는 실행하지 않았다. 오프라인 화면의 클립보드 응답은 모의이며 실제 Windows 클립보드는 브리지 단위 테스트로 검증했다.
- 기존 Windows 네이티브 폴더 선택창이 무반응이었던 정확한 원인은 미확정이다. 기존 Forge 경로 때문에 차단되는 조건은 없었으며, 해당 선택창 경로를 교체했다. 실행 앱에서 사용자 환경 재확인은 필요하다.
- 390px 반응형 화면은 확인했지만 실제 휴대전화 터치나 OS의 모션 줄이기 설정 전환은 실기기에서 실행하지 않았다. 관련 조건과 우선순위는 테스트로 확인했다.
- 모든 커스텀 노드의 메타데이터나 XYZ 축을 임의로 추측하지 않는다. 알 수 없는 그래프는 경고와 원문을 제공하며, 메타데이터 재사용은 원본 Comfy 워크플로 전체 복원을 의미하지 않는다.
- 앱 전체를 새 디자인으로 재작성한 것은 아니다. 이번 요청에 나온 카드·메뉴·대화 설정·네이티브 상단바·확인창에 변경을 한정했다.
