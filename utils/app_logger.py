# utils/app_logger.py
"""
앱 전역 로깅 시스템
"""
import os
import logging

_LOG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILE = os.path.join(_LOG_DIR, 'app.log')
_INITIALIZED = False


def _init_root():
    """루트 로거 초기화 (한 번만 실행)"""
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter('[%(asctime)s] %(name)s %(levelname)s: %(message)s',
                            datefmt='%H:%M:%S')

    # 파일 핸들러
    fh = logging.FileHandler(_LOG_FILE, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 콘솔 핸들러
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 반환"""
    _init_root()
    return logging.getLogger(name)
