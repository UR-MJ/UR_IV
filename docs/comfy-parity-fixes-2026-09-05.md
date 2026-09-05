# ComfyUI 수정 및 Forge 확장 검증 — 2026-09-05

## Image viewer: 리뷰 1~8 수정

| 항목 | 수정 내용 | 관련 구현 파일 |
| --- | --- | --- |
| 1. 인페인트 | 이미지와 마스크가 동일한 crop/contain 좌표 변환을 사용 | `comfy_custom_nodes/ai_studio_forge_parity/generation.py` |
| 2. Semantic v2 캐시 | conditioning 수명 동안 실행 정보를 보존하고 마지막 참조 해제 시 정리. 캐시 비활성화나 무제한 보존은 사용하지 않음 | `comfy_custom_nodes/ai_studio_forge_parity/anima38_cache.py` (추가), `anima38_nodes.py` |
| 3. 동명 리소스 | 정확한 LoRA/모델/TE/VAE 경로를 우선하며 모호한 파일명은 오류. Main/Hires의 폴더 경로 보존 | `core/comfy_workflow_compiler.py` |
| 4. 업스케일 배율 | 학습형 업스케일 결과를 원본 크기 × 요청 배율로 보정. EXIF 회전도 반영 | `core/comfy_workflow_compiler.py`, `backends/comfyui_backend.py` |
| 5. PAG | 정규화 이전 query 배율 대신 Attention 출력과 V를 보간. weak pass에만 적용 | `comfy_custom_nodes/ai_studio_forge_parity/guidance.py` |
| 6. 별도 negative CLIP | 명시적으로 분리한 negative 인코더 연결 보존 | `core/comfy_workflow_compiler.py` |
| 7. 단독 후처리 | 이전 이미지 후처리 단계만 교체하고 semantic bypass/negative 및 모델 설정 보존 | `backends/comfyui_backend.py` |
| 8. 워크플로 분석 | 번들 sampler/loader/semantic encoder/latent 인식. 생성된 v2 그래프 재입력, 값 변경, bypass와 모델 전환 지원. 기존 guidance와의 순환 참조 방지 | `backends/comfyui_workflow_inspector.py`, `backends/comfyui_backend.py`, `core/comfy_workflow_compiler.py` |

함께 수정한 패키지/문서 파일:

- `core/comfy_node_pack.py`, `comfy_custom_nodes/ai_studio_forge_parity/__init__.py`: 노드 팩 1.1.2.
- `comfy_custom_nodes/ai_studio_forge_parity/README.md`, `THIRD_PARTY_NOTICES.md`: 변경 내역과 로컬 캐시 어댑터 경계.
- `comfy_custom_nodes/ai_studio_forge_parity/LICENSES/comfyui-anima-3-8B-MIT.txt`: 고정 upstream 원문의 끝 빈 줄 복원. 검사값을 완화하지 않음.
- `.gitattributes`: 위 원문 파일의 LF 및 의도된 EOF 공백 보존.
- 이 문서 `docs/comfy-parity-fixes-2026-09-05.md`.

회귀 테스트 파일:

- `tests/test_comfy_backend_regressions.py` (추가)
- `tests/test_comfy_workflow_analysis.py` (추가)
- `tests/test_comfy_anima38_cache.py` (추가)
- `tests/test_forge_parity_mask_pag.py` (추가)
- `tests/test_comfy_workflow_compiler.py`
- `tests/test_comfy_anima38_compiler.py`
- `tests/test_comfy_anima38_nodes.py`

`vendor/`의 고정 upstream 코드 및 tokenizer 바이트는 변경하지 않았다.
`config/gallery_last_folder.txt`의 기존 개인 설정 변경은 이번 수정/커밋 대상이 아니다.

## Forge Classic 확장: 추가 확인 및 수정

대상: `C:\sd-webui-forge-classic\extensions\forge_sam3_extension`

| 수정 파일 | 내용 |
| --- | --- |
| `scripts/anima_safe_pag.py` | AND/영역/마스크 조건 및 low-VRAM 분할 실행에서 weak prediction을 Forge와 동일한 가중치·영역으로 합성. 모델 입력 전 내부 전달용 metadata 제거 |
| `tests/test_anima_safe_pag.py` | 실제 Forge sampling 함수로 가중 AND/영역/마스크 및 분할 실행 회귀 검증 |
| `scripts/anima_3_8b.py` | 예외 후 복구 시 이전 설치 processing을 우선 |
| `sam3ext/anima38/runtime.py` | 실제 설치 UNET 소유자를 저장하여 모델 전환 후에도 이전 connector 및 조건 캐시 해제 |
| `tests/test_anima38.py` | 예외 → 모델 전환 → bypass, sampling clone, 반복 복구 검증 |

확장의 기존 미커밋 작업은 유지하고 위 부분만 수정했다. Forge 본체 코드는 수정하지 않았다.
이 외부 저장소의 기존 작업 전체를 Image viewer 커밋에 묶거나 별도 커밋하지 않는다.

## 검증 범위 및 적용

- 앱 전체 테스트: 1,134개 중 1,131개 통과 / 3개 건너뜀 / 실패 0개.
- 앱 수정 Python 16개 파일 컴파일 및 변경분 공백 검사 통과.
- 실제 Comfy Cosmos Attention의 CUDA 연산에서 PAG standalone/suite 및 강도별 효과를 검증했다.
- Semantic v2는 실제 동봉된 conditioning 생성/forward 함수에 작은 테스트 호스트를 연결하여
  고정 negative + 128회 positive 변경, 폐기된 256개 결과의 메모리 수명, deepcopy/reload/예외 복구를 검증했다.
- Forge 전체 Python 테스트: 214개 중 213개 통과 / 1개 건너뜀 / 실패 0개.
- Forge 화면 스크립트 테스트 8/8 통과, 수정 Python 파일 컴파일 및 실제 sampler 합성 계약 검증 통과.
- 별도 교차 검토에서 배치 2 / low-VRAM / callback 중복 조합, private metadata 비유출,
  원본 conditioning 보존 및 lifecycle과의 공존도 검증했다.
- Vue 소스/화면/애니메이션은 변경하지 않으므로 프런트 빌드 대상이 아니다.
- 대형 모델의 실제 이미지 생성 A/B, 모든 확장 조합 및 장시간 GPU 생성은 이번 검증 범위 밖이다.
  다른 GPU 작업을 중단하거나 백엔드를 강제로 재시작하지 않는다.

설치된 앱 소유 노드 폴더도 1.1.2로 갱신했다:
`C:\ComfyUI_windows_portable_nvidia_v0310_Pack2\ComfyUI\custom_nodes\ai_studio_forge_parity`

설치본과 소스 fingerprint 일치, 두 번째 설치 시 변경 없음, 설치본의 31개 노드 등록과
Anima runtime 초기화를 확인했다. Python 변경은 앱/백엔드의 다음 시작부터 적용된다.
