# Danbooru runtime datasets

이 폴더의 Parquet은 Search와 Event Gen이 실제로 검색하는 로컬 런타임 데이터입니다.
대용량 파일은 Git에 넣지 않으며, 현재 설치에는 2026-07-13까지의 게시물을 담은
`2026_07` 릴리스가 적용되어 있습니다. 정확한 행 수, 스키마, 크기와 SHA-256은
`dataset_manifest.json`에서 확인합니다.

## 파일 역할

- `danbooru_2026_07_{g,s,q,e}.parquet`: Search용 전체 게시물 태그
- `danbooru_sorted/danbooru_{g,s,q,e}.parquet`: Event Gen용 parent-child 그래프
- `dataset_manifest.json`: 원본 revision과 8개 산출물의 검증 정보

Event shard에는 해당 등급 child와 그 child가 참조하는 모든 parent가 들어갑니다.
parent의 자체 등급이 달라도 포함되므로 단일 등급만 선택해도 그래프가 끊기지 않습니다.
여러 등급을 함께 불러올 때 생기는 parent 중복은 `EventDataLoader`가 ID 기준으로 제거합니다.

## 다시 생성하기

고정된 원본 revision을 받은 뒤 다음처럼 실행합니다.

```powershell
hf download nyanko-devs/danbooru2026 metadata/posts-snapshot.parquet `
  --repo-type dataset `
  --revision ebb02a630201c7b51487e45fb90b3fcf4cbedc20 `
  --local-dir .cache/danbooru2026

.\venv\Scripts\python.exe tools\refresh_danbooru_data.py posts `
  --source .cache/danbooru2026/metadata/posts-snapshot.parquet `
  --output-dir danbooru_optimized `
  --dataset-label 2026_07 `
  --source-url https://huggingface.co/datasets/nyanko-devs/danbooru2026 `
  --source-revision ebb02a630201c7b51487e45fb90b3fcf4cbedc20 `
  --snapshot-at 2026-07-13T16:25:53.082Z `
  --expected-source-sha256 5b6b2671dc0fa966de71af76dfd342f485f76581447cec9e26c313ba9fb1c2fd
```

생성 결과만 다시 검사하려면:

```powershell
.\venv\Scripts\python.exe tools\refresh_danbooru_data.py validate `
  --manifest danbooru_optimized/dataset_manifest.json `
  --root danbooru_optimized
```
