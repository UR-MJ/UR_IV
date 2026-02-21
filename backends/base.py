# backends/base.py
"""백엔드 추상 인터페이스 및 공통 데이터 클래스"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable


@dataclass
class BackendInfo:
    """백엔드에서 가져온 서버 정보"""
    models: List[str] = field(default_factory=list)
    samplers: List[str] = field(default_factory=list)
    schedulers: List[str] = field(default_factory=list)
    upscalers: List[str] = field(default_factory=list)
    vae: List[str] = field(default_factory=lambda: ["Use same VAE"])
    checkpoints: List[str] = field(default_factory=list)
    options: Dict = field(default_factory=dict)


@dataclass
class GenerationResult:
    """통합 생성 결과"""
    success: bool
    image_data: Optional[bytes] = None
    info: Dict = field(default_factory=dict)
    error: Optional[str] = None


# progress_callback 타입: (step: int, total_steps: int, preview_bytes: Optional[bytes]) -> None
ProgressCallback = Callable[[int, int, Optional[bytes]], None]


class AbstractBackend(ABC):
    """백엔드 추상 클래스"""

    def __init__(self, api_url: str):
        self.api_url = api_url

    @abstractmethod
    def test_connection(self) -> bool:
        """연결 상태 확인"""
        ...

    @abstractmethod
    def get_info(self) -> BackendInfo:
        """서버 정보 (모델, 샘플러 등) 가져오기"""
        ...

    @abstractmethod
    def txt2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """텍스트→이미지 생성"""
        ...

    @abstractmethod
    def img2img(self, model_name: str, payload: Dict,
                progress_callback: Optional[ProgressCallback] = None) -> GenerationResult:
        """이미지→이미지 생성"""
        ...

    @abstractmethod
    def upscale(self, image_b64: str, settings: Dict) -> str:
        """이미지 업스케일. base64 결과 반환"""
        ...

    @abstractmethod
    def adetailer(self, image_b64: str, settings: Dict) -> str:
        """ADetailer 처리. base64 결과 반환"""
        ...

    def get_loras(self) -> List[Dict]:
        """LoRA 목록 반환. 각 항목: {'name': str, 'alias': str, 'path': str}"""
        return []

    def get_system_stats(self) -> Dict:
        """GPU/VRAM 상태 조회. 기본 구현은 빈 dict 반환"""
        return {}

    @abstractmethod
    def get_backend_type(self) -> str:
        """백엔드 이름 반환 ('webui' 또는 'comfyui')"""
        ...
