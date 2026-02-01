# CLAUDE.md - Claude Code 행동 지침

## 프로젝트 개요
PyQt6 기반 이미지 생성 애플리케이션. Danbooru 데이터셋을 활용한 태그 필터링, favorites 시스템, 이벤트 생성 기능 포함.

---

## 🤖 Gemini CLI 활용 규칙

### 언제 Gemini를 사용할 것
아래 상황에서는 직접 처리하지 말고 `gemini` 명령어를 실행하여 정보를 얻어라:

1. **대량 파일 분석**
   - 5개 이상의 파일을 동시에 읽어야 할 때
   - 프로젝트 전체 구조 파악이 필요할 때
   ```bash
   gemini chat "이 프로젝트의 전체 구조를 분석해줘" --no-stream
   ```

2. **최신 정보 검색**
   - PyQt6, PySide6, pandas 등 라이브러리의 최신 API 정보
   - 에러 메시지의 최신 해결책 검색
   ```bash
   gemini chat "PyQt6 QGraphicsView 성능 최적화 최신 방법" --no-stream
   ```

3. **긴 문서/코드 요약**
   - 100줄 이상의 파일 내용 요약이 필요할 때
   - 복잡한 클래스 구조 파악
   ```bash
   gemini chat "@파일경로 이 파일의 핵심 로직만 요약해줘" --no-stream
   ```

4. **1차 코드 리뷰**
   - 내가 작성한 코드의 잠재적 문제점 검토
   ```bash
   gemini chat "@파일경로 이 코드에서 메모리 누수나 예외 처리 누락 찾아줘" --no-stream
   ```

### Gemini 명령어 형식
```bash
# 단순 질문
gemini chat "질문 내용" --no-stream

# 파일 참조 질문
gemini chat "@파일경로 질문 내용" --no-stream

# 여러 파일 참조
gemini chat "@파일1 @파일2 비교 분석해줘" --no-stream
```

### 주의사항
- Gemini 응답을 그대로 사용하지 말고, 검토 후 필요시 수정하여 적용할 것
- 핵심 로직 구현은 내가 직접 할 것 (Gemini는 정보 수집용)
- Gemini 호출 실패 시 직접 처리로 전환

---

## 📁 프로젝트 구조 참고

```
project/
├── main_ui.py          # 메인 애플리케이션
├── tabs/               # 탭 컴포넌트들
├── utils/              # 유틸리티 함수
├── data/               # 데이터 로더
└── config/             # 설정 파일
```

---

## 🔧 코딩 스타일

- PyQt6 시그널/슬롯 패턴 사용
- 타입 힌트 필수
- 독스트링은 한글로 작성
- 에러 처리는 try-except로 명시적으로

---

## 💡 자주 쓰는 Gemini 활용 예시

```bash
# 프로젝트 전체 파악
gemini chat "@. 이 프로젝트에서 이미지 로딩 관련 코드가 어디 있는지 찾아줘" --no-stream

# 버그 원인 추적
gemini chat "@main_ui.py @utils/loader.py 이 두 파일 사이에서 데이터 흐름 분석해줘" --no-stream

# 최신 해결책 검색
gemini chat "PyQt6 QThread에서 GUI 업데이트 시 프리징 해결 방법 2024" --no-stream
```

## Git 자동화 규칙
- 파일 수정 완료 후 반드시 commit & push 수행
- 커밋 메시지 형식 (한글):
  - feat: 새 기능
  - fix: 버그 수정
  - refactor: 리팩토링
  - docs: 문서 수정