import os
from urllib.parse import urlparse

import warnings

from PIL import Image
# 대형 업스케일 결과(8K+)는 PIL 기본 한도(~178MP)를 넘으므로 상한을 올리되,
# 무제한(None) 대신 유한 상한으로 손상/폭주 이미지의 OOM은 차단.
Image.MAX_IMAGE_PIXELS = 1_000_000_000  # 1기가픽셀 (32K×32K급)
warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)

from PyQt6.QtGui import QImageReader
QImageReader.setAllocationLimit(4096)  # MB 단위 — 16K RGBA 직전까지 허용 (기본 256MB는 8K RGBA도 초과)

# QtWebEngine은 QApplication 생성 전에 import 필요
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from core.storage_paths import config_file, storage_paths, user_data_file

# --- [설정 상수] ---
USER_INPUT_URL = "http://127.0.0.1:7860/?__theme=dark"

_p = urlparse(USER_INPUT_URL)
WEBUI_API_URL = f"{_p.scheme}://{_p.netloc}"
if not _p.scheme:
    WEBUI_API_URL = f"http://{_p.path}"

COMFYUI_API_URL = "http://127.0.0.1:8188"
COMFYUI_WORKFLOW_PATH = ""
COMFYUI_WORKFLOW_IMG2IMG_PATH = ""

from utils.app_logger import get_logger as _get_logger
_logger = _get_logger('config')
_logger.info(f"초기 설정된 API 주소: {WEBUI_API_URL}")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CURRENT_DIR, 'generated_images')

# ── 애플리케이션 소유 저장 경계 ──
# config = 설정/경로, user_data = 프리셋·즐겨찾기 같은 사용자 작성 데이터.
# 위치 결정과 레거시 이동은 traversal-safe 중앙 모듈 한 곳에서 담당한다.

USER_DATA_DIR = str(storage_paths.user_data_dir)
os.makedirs(USER_DATA_DIR, exist_ok=True)
_USER_DATA_FILES = (
    'character_presets.json', 'event_gen_settings.json', 'favorite_tags.json',
    'favorites.json', 'prompt_history.json', 'prompt_presets.json',
    'search_tab_settings.json',
)
for _n in _USER_DATA_FILES:
    try:
        user_data_file(_n, legacy_paths=_n)
    except OSError as _exc:
        _logger.warning("사용자 데이터 이전 실패 (%s): %s", _n, _exc)


def user_data_path(name: str) -> str:
    """user_data/ 내 파일 경로 반환 (사용자 상태 JSON 통합용)."""
    return str(user_data_file(name))


PROMPT_SETTINGS_FILE = str(config_file(
    'prompt_settings.json',
    legacy_paths=('user_data/prompt_settings.json', 'prompt_settings.json'),
))
CACHE_DIR = os.path.join(CURRENT_DIR, 'image_cache')
THUMB_DIR = os.path.join(CACHE_DIR, 'thumbs')
os.makedirs(THUMB_DIR, exist_ok=True)
DB_FILE = os.path.join(CURRENT_DIR, 'photodata.sqlite')
FAVORITES_FILE = user_data_path('favorites.json')
# ★★★ 검색 탭용 Parquet (기존) ★★★
PARQUET_DIR = os.path.join(CURRENT_DIR, 'danbooru_optimized')

# ★★★ 이벤트 생성 탭용 Parquet (parent_id 포함) ★★★
EVENT_PARQUET_DIR = os.path.join(PARQUET_DIR, 'danbooru_sorted')
