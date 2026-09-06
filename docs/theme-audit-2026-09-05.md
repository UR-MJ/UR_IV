# 설정 테마 불일치 점검 — 2026-09-05

## 결론과 범위

종료 확인창의 검정/노랑 고정 스타일을 포함하여 실제 테마 불일치를 확인했다. 이번 작업은 **점검만** 수행했으며 제품 코드, 개인 설정, 기존 빌드 결과는 변경하지 않았다. 수정·커밋·푸시는 하지 않았다.

- 실제 Vue App과 14개 주요 라우트를 네트워크/파일 쓰기 없는 임시 메모리 브릿지로 렌더링했다. 라이트 기본 화면: T2I, I2I, Inpaint, Event Gen, Search, XYZ Plot, Creator, 대화, Editor, Batch/Upscale, Gallery, Favorites, PNG Info, Settings.
- Search 결과, Favorites 상세창, Editor 이미지/보정 패널, XYZ 입력 오류, 드롭다운 hover를 합성 데이터로 추가 확인했다. 주요 화면 배경은 대체로 테마를 따랐다. 빈 화면 확인만으로 데이터가 있는 모든 상태까지 검증한 것은 아니다.
- 실제 PyQt 위젯과 현재 메서드를 offscreen/Fusion으로 실행하여 팝업·메뉴·라이트/다크 전환을 검사했다. 원인 분리를 위한 임시 스타일 변경은 테스트 프로세스 메모리에만 적용했다.
- 현재 실행 중인 AI Studio 창을 찾지 못해 완성 앱을 재시작하거나 백엔드를 켜지 않았다. 실제 Windows 네이티브 파일 선택창, 외부 Web/Backend 페이지 내용, 모든 Settings 하위 설정과 작업 중 상태까지 전수 검증한 것은 아니다.

## 확인된 문제

| 우선순위 | 위치 | 재현된 문제 | 원인/소스 |
|---|---|---|---|
| 높음 | 앱 종료 확인창 | 라이트에서도 검정 배경과 노랑 기본 버튼. 사용자 첨부 화면과 동일 | `ui/generator_main.py:2493`의 로컬 QMessageBox/QPushButton 고정 색상 |
| 중간 | 시스템 트레이 메뉴 | 다크→라이트 전환 후에도 이전 다크 색상을 유지 | `utils/tray_manager.py:41`에서 최초 생성 시에만 색상을 적용. `ui/native_dialogs.py:61`의 갱신 대상에 트레이가 없음 |
| 높음 | 트레이 및 Settings의 프롬프트 히스토리 메뉴 | 선택 항목의 배경만 강조색이 되고 글자는 본문 색상으로 남아 대비가 낮음 | `utils/tray_manager.py:45`, `ui/generator_ui_setup.py:768` |
| 높음 | Search 태그 및 분류 범례 | 흰 배경에서 노랑/연두 등 일부 태그가 매우 희미함. 테마의 태그 색상 설정도 사용하지 않음 | `frontend/src/views/SearchView.vue:1274` 이후 고정 분류 팔레트 |
| 중간 | Favorites 상세창의 Prompt/Negative/Parameters 복사 아이콘 | 라이트 모드에서 어두운 반투명 버튼 위 어두운 아이콘. hover 시에도 대비가 낮음 | `frontend/src/views/FavoritesView.vue:440`의 고정 검정 배경과 테마 본문/강조색 조합 |
| 낮음 | I2I 디노이즈 슬라이더 | 강조색이 금색인데 해당 슬라이더만 브라우저 기본 파란색 | `frontend/src/views/I2IView.vue:64`는 `accent-color: auto`, 같은 화면 Steps/CFG는 `modern-slider`로 테마 색상 적용 |
| 중간 | 공통 드롭다운 — 사용자 지정 강조색 | 라이트+흰 강조색에서 미선택 항목에 hover하면 흰 배경에 흰 글자로 사라짐. 선택된 항목은 정상 | `frontend/src/components/CustomSelect.vue:245`와 다음 active 규칙이 원시 `--accent`를 글자색으로 사용 |
| 중간 | Editor 보정 — 사용자 지정 상태색 | `state-ok`/`state-alert`를 흰색으로 지정하면 ‘자동 보정’/‘필터 해제’가 흰 배경+흰 글자 | `frontend/src/components/editor/ColorPanel.vue:242`, `:290`의 상태 배경 + 고정 흰 글자 |
| 낮음 | XYZ Plot 입력 오류 | 오류 상태색을 바꿔도 오류 문구는 계속 동일한 빨강 | `frontend/src/views/XYZPlotView.vue:271`이 정의되지 않은 `--error`의 고정 fallback을 사용 |
| 낮음/예외 경로 | 시작 실패 Boot Error | 다크 설정에서도 기본 회색/검정 OS/Qt 팔레트로 표시 | `ui/generator_main.py:174`의 부모 없는 `QMessageBox.critical(None, ...)` |

사용자 지정 흰색 사례는 경계값 점검이며 현재 저장된 개인 설정은 `light`, 색상 override 없음이었다. 기본 설정에서 이미 발생하는 종료창·태그·메뉴 문제와 구분해야 한다.

## 재현 근거

- 종료창: 기대 라이트 배경 `#F4F4F2`, 실제 `#0D0D0D`. 현재 closeEvent의 실제 QMessageBox로 실패 assertion을 재현했다. 테스트 창의 로컬 stylesheet만 제거하면 light/default/dark에서 각각 `#F4F4F2`/`#0A0A0A`/`#050505`로 돌아왔다. 이 문제는 Vue↔Python 동기화 누락이 아니라 팝업 자체의 override다.
- 트레이: 다크→라이트 후에도 실제 배경 `#1E1E1E`, 기대값 `#E9E9E6`. 메뉴가 새 테마를 받지 않는다.
- 선택 메뉴: 실제 렌더 픽셀에 라이트 `#1B1B19` 글자/`#775C00` 배경, 다크 `#FFFFFF` 글자/`#FACC15` 배경이 존재했다. 대비는 각각 약 2.72:1 / 1.53:1. 테스트 메모리에서만 `accent_fill`+`on_accent` 쌍을 적용하면 약 6.33:1 / 12.93:1로 개선됐다.
- Search: 실제 DOM에서 작가 태그 `rgb(250,204,21)`/5% 동색 배경, 표정 범례 `rgb(251,191,36)`/10% 동색 배경 확인. 흰 바탕 합성 대비는 각각 약 1.49:1 / 1.45:1이고 스크린샷에서도 희미했다.
- Favorites: hover 전환 완료 후 실제 배경 `rgba(45,45,45,.9)`, 아이콘 `rgb(119,92,0)`, opacity 1. 라이트의 어두운 금색 아이콘과 어두운 배경이 충돌한다.
- CustomSelect: 라이트 배경을 확인한 상태에서 hover 항목의 실제 흰 글자/흰 반투명 배경/흰 부모 배경 확인. 대비 1:1. ‘선택됨’의 `accent-fill`/`on-accent` 조합은 유지됐다.
- Editor: 실제 보정 패널의 두 버튼 모두 computed foreground/background가 `rgb(255,255,255)`인 것을 확인했다.
- XYZ: 실제 `--state-alert: #FFFFFF`, `--state-alert-fg: #6E6E6E`인데 축 오류 문구는 `rgb(216,92,92)`로 남았다. 생성 요청 없이 잘못된 축 값 입력으로 확인했다.

## 정상 확인/제외한 부분

- 부모가 있는 일반 QMessageBox/QInputDialog, 테마 지원 Qt 폴더 선택창, Web JavaScript confirm/prompt의 라이트 배경은 격리 Qt 검사에서 정상.
- Splash의 라이트 카드 배경은 정상. 가중치 모달의 다크 배경도 브라우저에서 정상.
- 이미지 캔버스, 반투명 모달 뒤막, 마스크, 만화의 흰 종이, 외부 사이트 자체 테마 등 의도적인 색상은 결함으로 분류하지 않았다.
- 구형 위젯의 고정 색상은 현재 UI에서 실제 사용되는 경로가 확인되지 않으면 확정 목록에 넣지 않았다.

## 소스에서 발견했지만 추가 화면 검증이 필요한 후보

- `frontend/src/styles/galleryShared.css:205`: 이미지 오버레이 작은 버튼 hover가 원시 강조색 배경 + 검정 아이콘이어서 짙은 사용자 강조색에서 대비가 낮아질 수 있다.
- `frontend/src/styles/galleryShared.css:387`, `frontend/src/components/CompareSlider.vue:85`: 반투명 검정 안내 배경에 일반 테마의 muted 글자색을 사용. 밝은 이미지/라이트 테마 조합의 실제 화면 확인이 추가로 필요하다.
- `frontend/src/views/I2IView.vue:53`: Krea2 아이덴티티 유지도 슬라이더도 디노이즈와 같은 스타일 누락 구조지만 Krea2 화면에서는 직접 재현하지 않았다.
- Windows 기본 파일 선택창을 그대로 사용하는 다른 호출은 OS 테마와 앱 테마가 다를 때 별도 점검이 필요하다.

## 실행한 검사

```powershell
.\venv\Scripts\python.exe -X utf8 -m unittest tests.test_native_shell tests.test_theme_contract tests.test_ui_copy_contract -q
# 33 passed

cd frontend
npm run test -- src/theme/applyTheme.test.ts
# 18 passed
```

기존 테스트 총 51개 통과. 별도의 실제 Qt 재현 probe는 확인된 결함 때문에 의도대로 실패(exit 1)했다. 테스트 통과를 UI 결함 없음으로 해석하면 안 된다. 제품 변경이 없어 빌드하지 않았다.

임시 브라우저 fixture 두 파일과 점검 서버는 점검 후 정리했다. 기존 다른 작업의 수정/빌드 파일은 건드리지 않았다. `config/ui_prefs.json` 및 `config/gallery_last_folder.txt`의 점검 전후 SHA-256 동일성을 확인했다.

## 권장 수정 순서 — 아직 미적용

1. 종료창의 자체 고정 스타일 제거 및 공통 네이티브 테마 적용. 트레이 메뉴에도 테마 변경 전달.
2. 메뉴 선택 배경/글자색을 짝지어 적용하고 팝업별 회귀 검사 추가.
3. Search 분류 수를 유지한 채 라이트/다크용 읽기 쉬운 팔레트 제공. Favorites 복사 버튼도 배경과 아이콘 색을 함께 수정.
4. 사용자 지정 강조색/상태색에서 글자와 배경의 대비를 보장. I2I 슬라이더와 XYZ 오류를 올바른 테마 토큰에 연결.
5. 실제 앱에서 Windows 파일 선택창, Web/Backend 상단 바, 전체 Settings 하위 항목과 작업 중 팝업을 마지막으로 재검증.

## 점검 이후: 미리보기 복구

사용자가 미리보기 파일을 다시 열 수 있도록 `frontend/dev/theme-audit.html`과 `.js`를 복구했다. 더 이상 일회성 정리 대상으로 삭제하지 않는다. `frontend/dev/start-theme-preview.cmd`로 개발 서버를 시작하고 `http://127.0.0.1:5174/dev/theme-audit.html`로 연다. 자세한 실행 방법과 제한은 `frontend/dev/THEME-PREVIEW.md`에 정리했다. 이는 미리보기 접근 복구이며, 위에서 발견한 제품 UI 결함을 수정했다는 뜻은 아니다.
