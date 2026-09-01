# Tag database

이 폴더는 Search 탭의 결과 태그 분류·색상 표시·제외 규칙, 태그 자동완성,
캐릭터 특징과 Character Insight에 사용하는 런타임 데이터입니다. 실제 게시물 검색
대상은 별도 `danbooru_optimized/` 폴더이며, 이 폴더는 검색 결과를 해석하는 사전입니다.

파일 경로와 필수 스키마의 단일 소스는 `manifest.json`입니다. Python 코드는 파일명을
직접 조합하지 않고 `core.tag_database.TagDatabase` 인터페이스를 통해 접근합니다.

## 폴더 구성

| 폴더 | 용도 |
|---|---|
| `autocomplete/` | 태그 자동완성, 유형, 사용 횟수, 별칭 |
| `catalogs/` | 한국어 태그 정보와 등급별 통계 |
| `characters/` | 캐릭터 외형·의상·작품·대표 프롬프트 데이터 |
| `lexicons/` | 수동 선별(curated) 및 확장(extended) 태그 목록 |
| `taxonomy/` | Wiki 그룹, implication, UI 분류표 |

## 데이터 선택 기준

- `curated`와 `extended` 목록은 서로 완전한 포함 관계가 아니므로 둘 다 보존합니다.
- 기존 89개 Wiki 그룹 Parquet는 동일 원본을 쪼갠 파일이어서
  `taxonomy/danbooru_tag_groups.parquet` 하나로 통합했습니다.
- Wiki 문서 링크·URL·목록 페이지 같은 44개 수집 부산물과 322개 중복 행은 통합 시
  제거했습니다.
- implication은 삭제·폐기 상태를 제외한 활성 관계만 보존하며, 프롬프트를 임의로
  추가하지 않고 분류 보강과 중복 태그 제거에만 사용합니다.
- Character Insight 원본의 설명이 비어 있던 1개 행은 사용할 수 없어 제거했습니다.
- 캐릭터 특징/Insight 내부의 반복 태그와 소형 사전의 중복 줄은 첫 등장 순서를
  유지하며 하나로 줄였습니다.
- 캐릭터 작품 매핑은 `character_profiles` → 수동 선별 별칭 매핑 → Danbooru 확장
  매핑 순으로 적용하여 기존 결과를 우선합니다.

## 유지보수

데이터를 교체한 뒤에는 다음 검증을 실행합니다.

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_tag_database
.\venv\Scripts\python.exe run_tests.py
```

`danbooru wiki/` 같은 원본 다운로드 작업 폴더는 런타임 자산이 아닙니다. 필요한 자료를
정제해 이 폴더와 manifest에 편입한 뒤 원본 작업 폴더는 제거합니다.
