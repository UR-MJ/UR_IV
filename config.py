import sys
import os
import json
import time
import base64
import requests
import random
import hashlib
import re
import shutil
import sqlite3
import logging
import unittest
import pandas as pd
from urllib.parse import urlparse
from pathlib import Path
from PIL import Image, PngImagePlugin
from threading import Lock
from typing import Optional, List, Dict, Tuple
from core.database import MetadataManager
from concurrent.futures import ThreadPoolExecutor
import exifread

# [UI 라이브러리 임포트]
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QMessageBox, QLineEdit, QSlider, QFrame,
    QSizePolicy, QComboBox, QGroupBox, QCheckBox, QSplitter, QScrollArea,
    QStatusBar, QLayout, QFileDialog, QListWidget, QListWidgetItem, QDialog,
    QTabWidget, QRadioButton, QStackedWidget, QButtonGroup, QTableWidget,
    QTableWidgetItem, QHeaderView, QGridLayout
)
from PyQt6.QtGui import QPixmap, QFont, QImage, QIcon, QColor, QCursor, QPainter, QPen, QPolygon, QBrush, QAction
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QEvent, QSize, QUrl, QRect, QPoint, QTimer

# [기능 확장 라이브러리]
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile, QWebEngineScript

import cv2
import numpy as np

# --- [설정 상수] ---
USER_INPUT_URL = "http://127.0.0.1:7860/?__theme=dark"

_p = urlparse(USER_INPUT_URL)
WEBUI_API_URL = f"{_p.scheme}://{_p.netloc}"
if not _p.scheme:
    WEBUI_API_URL = f"http://{_p.path}"

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
