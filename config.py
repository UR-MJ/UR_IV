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

# ── 사용자 상태 JSON 통합 폴더 ──
# 루트에 흩어져 있던 사용자 상태 파일(history/presets/favorites/settings 등)을
# user_data/ 하나로 모음. import 시 1회 자동 마이그레이션 — 기존 루트 파일을
# user_data/로 이동해 데이터 보존. config.py는 거의 최초로 import되므로 다른
# 모듈이 파일을 읽기 전에 이전이 끝남.
USER_DATA_DIR = os.path.join(CURRENT_DIR, 'user_data')
os.makedirs(USER_DATA_DIR, exist_ok=True)
_USER_DATA_FILES = (
    'character_presets.json', 'event_gen_settings.json', 'favorite_tags.json',
    'favorites.json', 'prompt_history.json', 'prompt_presets.json',
    'prompt_settings.json', 'search_tab_settings.json',
)
for _n in _USER_DATA_FILES:
    _old = os.path.join(CURRENT_DIR, _n)
    _new = os.path.join(USER_DATA_DIR, _n)
    if os.path.exists(_old) and not os.path.exists(_new):
        try:
            import shutil as _shutil
            _shutil.move(_old, _new)
        except Exception:
            pass


def user_data_path(name: str) -> str:
    """user_data/ 내 파일 경로 반환 (사용자 상태 JSON 통합용)."""
    return os.path.join(USER_DATA_DIR, name)


PROMPT_SETTINGS_FILE = user_data_path('prompt_settings.json')
CACHE_DIR = os.path.join(CURRENT_DIR, 'image_cache')
THUMB_DIR = os.path.join(CACHE_DIR, 'thumbs')
os.makedirs(THUMB_DIR, exist_ok=True)
DB_FILE = os.path.join(CURRENT_DIR, 'photodata.sqlite')
FAVORITES_FILE = user_data_path('favorites.json')
# ★★★ 검색 탭용 Parquet (기존) ★★★
PARQUET_DIR = os.path.join(CURRENT_DIR, 'danbooru_optimized')

# ★★★ 이벤트 생성 탭용 Parquet (parent_id 포함) ★★★
EVENT_PARQUET_DIR = os.path.join(PARQUET_DIR, 'danbooru_sorted')
