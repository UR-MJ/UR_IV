import os
from urllib.parse import urlparse

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

from PyQt6.QtGui import QImageReader
QImageReader.setAllocationLimit(0)  # Qt 이미지 할당 제한 해제

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
PROMPT_SETTINGS_FILE = os.path.join(CURRENT_DIR, 'prompt_settings.json')
CACHE_DIR = os.path.join(CURRENT_DIR, 'image_cache')
THUMB_DIR = os.path.join(CACHE_DIR, 'thumbs')
os.makedirs(THUMB_DIR, exist_ok=True)
DB_FILE = os.path.join(CURRENT_DIR, 'photodata.sqlite')
FAVORITES_FILE = os.path.join(os.path.dirname(__file__), "favorites.json")
# ★★★ 검색 탭용 Parquet (기존) ★★★
PARQUET_DIR = os.path.join(CURRENT_DIR, 'danbooru_optimized')

# ★★★ 이벤트 생성 탭용 Parquet (parent_id 포함) ★★★
EVENT_PARQUET_DIR = os.path.join(PARQUET_DIR, 'danbooru_sorted')
