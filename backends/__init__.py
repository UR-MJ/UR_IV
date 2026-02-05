# backends/__init__.py
"""백엔드 팩토리 및 전역 관리"""
from enum import Enum
from typing import Optional

from backends.base import AbstractBackend, BackendInfo, GenerationResult


class BackendType(Enum):
    WEBUI = "webui"
    COMFYUI = "comfyui"


_current_backend: Optional[AbstractBackend] = None
_current_type: BackendType = BackendType.WEBUI


def get_backend() -> AbstractBackend:
    """현재 활성 백엔드 반환 (없으면 WebUI 기본 생성)"""
    global _current_backend
    if _current_backend is None:
        from backends.webui_backend import WebUIBackend
        import config
        _current_backend = WebUIBackend(config.WEBUI_API_URL)
    return _current_backend


def set_backend(backend_type: BackendType, api_url: str):
    """백엔드 전환"""
    global _current_backend, _current_type
    _current_type = backend_type
    api_url = api_url.strip()

    if backend_type == BackendType.WEBUI:
        from backends.webui_backend import WebUIBackend
        _current_backend = WebUIBackend(api_url)
        import config
        config.WEBUI_API_URL = api_url
    elif backend_type == BackendType.COMFYUI:
        from backends.comfyui_backend import ComfyUIBackend
        _current_backend = ComfyUIBackend(api_url)
        import config
        config.COMFYUI_API_URL = api_url


def get_backend_type() -> BackendType:
    """현재 백엔드 타입 반환"""
    return _current_type


def set_backend_type_silent(backend_type: BackendType):
    """백엔드 타입만 설정 (인스턴스 생성 없음, 설정 복원용)"""
    global _current_type
    _current_type = backend_type
