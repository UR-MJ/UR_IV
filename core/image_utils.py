# core/image_utils.py
import os
import re
import hashlib
from pathlib import Path

def normalize_path(path):
    """경로를 정규화된 POSIX 형식으로 변환"""
    return Path(path).resolve().as_posix()

def normalize_windows_path(path):
    """Windows 경로 정규화"""
    if path.startswith('\\\\?\\') or path.startswith('//?/'):
        path = re.sub(r'^\\\\\?\\', '', path)
        path = re.sub(r'^//\?/', '', path)
    return os.path.normpath(path)

def move_to_trash(path):
    """파일을 휴지통으로 이동"""
    try:
        from send2trash import send2trash
        path = normalize_windows_path(path)
        if os.path.exists(path):
            send2trash(path)
        else:
            print(f"휴지통 이동 실패: 파일이 존재하지 않음 {path}")
    except ImportError:
        try:
            path = normalize_windows_path(path)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"파일 삭제 실패: {e}")

def get_thumb_path(image_path):
    """썸네일 경로 생성"""
    from config import THUMB_DIR
    h = hashlib.sha1(normalize_path(image_path).encode('utf-8')).hexdigest()
    return os.path.join(THUMB_DIR, f"{h}.jpg")

def read_exif(image_path, generation_info):
    """EXIF 정보 읽기"""
    if not generation_info:
        return {"Error": "이 이미지에 대한 생성 정보가 없습니다."}
    return generation_info

def exif_for_display(exif_data):
    """EXIF 데이터를 표시용 문자열로 변환"""
    if not exif_data or "Error" in exif_data:
        return "표시할 생성 정보가 없습니다."
    prompt = exif_data.get('prompt', 'N/A')
    neg_prompt = exif_data.get('negative_prompt', 'N/A')
    return f"Prompt: {prompt}\n\nNegative Prompt: {neg_prompt}"