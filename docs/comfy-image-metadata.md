# ComfyUI 이미지 메타데이터 읽기

Gallery와 PNG Info는 `core.image_metadata.read_metadata_for_ui()`의 같은 결과를 사용한다. 이미지 파일은 읽기만 하며 모델, 워크플로 노드, 서버를 실행하지 않는다.

## 읽는 정보

- PNG `prompt` API 그래프가 우선이고, 없으면 `workflow`의 링크와 알려진 위젯 배치를 사용한다.
- 저장/미리보기 노드로 이어진 샘플러의 positive/negative 연결을 추적한다. 노드 번호·배열 순서·제목으로 역할을 추측하지 않는다.
- KSampler 계열, SamplerCustom/Advanced의 CFGGuider·BasicGuider, CLIP/SDXL/Flux 인코더, 앱의 Anima semantic 인코더, 알려진 Conditioning·ControlNet 연결을 읽는다.
- Seed, Steps, CFG, Sampler, Scheduler, Denoise, Model, Latent 크기는 연결에서 확정할 수 있는 값만 제공한다.
- JPEG/WebP의 EXIF UserComment와 기존 A1111/Forge `parameters`도 유지한다. A1111 정보와 Comfy JSON이 함께 있으면 A1111 표시가 우선이고 Comfy 원문은 별도로 보존한다.

## 모호한 경우

여러 샘플러의 문장, SDXL/Flux의 서로 다른 인코더 문장, 혼합 conditioning은 합치거나 하나를 선택하지 않는다. 공통으로 확정된 문장·설정만 정규화하며, 전체 자동 적용이 안전하지 않으면 `can_apply=false`로 T2I 전송/즉시 생성을 차단한다. 후보별 원문을 따로 보고 복사할 수 있다.

알 수 없는 커스텀 노드, 동적 텍스트 생성, muted/bypass 의미, subgraph, 잘못된 링크는 경고와 원본 JSON을 남긴다. 이 기능은 기본 문장·설정의 재사용이지 ComfyUI 워크플로 전체 복원이 아니다.

JSON 8 MiB, 노드 4,096개, 연결 깊이 96, 후보 128개 및 탐색 예산을 제한한다. 그래프 문자열을 평가하거나 참조 파일/URL을 열지 않는다.

## UI 및 보존

PNG Info에 Prompt만/Negative만 복사 버튼을 항상 보이도록 제공한다. Qt 데스크톱과 웹 단말의 공통 클립보드 함수를 사용하고 실제 성공일 때만 성공 알림을 표시한다. 원본 `prompt`/`workflow` JSON은 각각 펼쳐 보기와 복사가 가능하다.

Gallery의 Comfy 메타데이터는 읽기 전용이다. 기존 A1111 EXIF 편집기는 유지하되 Comfy 그래프를 A1111 텍스트로 덮어쓰지 않는다. 메타데이터 이식에서도 원본 Comfy 청크가 있는 경우 합성 `parameters`를 만들어 출처를 바꾸지 않는다.

`read_metadata_for_ui()`는 기존 `raw`, `prompt`, `negative`, `params_line`, `path`, `filename`, `size` 필드를 유지한다. 추가 필드는 `source`, `parameters`, `raw_prompt`, `raw_workflow`, `metadata_warnings`, `prompt_candidates`, `can_apply`, `metadata_ambiguous`이다.

Comfy 즉시 생성과 히스토리 큐 추가는 표시용 `params_line`을 다시 텍스트 파싱하지 않고 확정된 `parameters`를 사용한다. 즉시 생성은 원래 시드를, 큐 추가는 새 변형용 `-1`을 사용한다. 현재 모델·LoRA는 유지하며 메타데이터의 모델 경로로 자동 변경하거나 다운로드하지 않는다. PNG Info·Gallery 전송 및 히스토리 당겨오기에서도 모호한 그래프의 부분 프롬프트를 자동 적용하지 않는다.

## 검증

`tests/test_image_metadata.py`는 작은 임시 PNG/JPEG/WebP를 생성하여 실제 추출 함수를 검증하고 원본 바이트가 변하지 않는지 확인한다. API/워크플로 그래프, 순서에 의존하지 않는 역할 추적, 다중 샘플러, SDXL, custom advanced guider, ControlNet, Anima, 순환/미지 노드, 손상 JSON, A1111 공존, EXIF 및 Comfy 이식을 포함한다.

`frontend/src/components/ComfyMetadataDetails.test.ts`는 후보 표시와 원본 JSON의 HTML 이스케이프를 검증한다. 모델 다운로드나 GPU 생성 결과를 검증하는 테스트는 아니다.

`tests/test_comfy_metadata_actions.py`는 실제 브릿지 읽기와 Vue 액션을 작은 임시 PNG 및 가짜 화면·생성 경계에서 연결해 검증한다. 모호한 정보의 적용 차단, 원문 JSON과 파라미터가 프롬프트로 섞이지 않는지, 원래 모델·LoRA 보존, 공통 설정·시드 전달 및 기존 WebUI 동작을 확인한다. 실제 생성이나 서버 연결은 실행하지 않는다.
