# core/edge_refiner.py
"""배경 제거 후 알파 채널 정제 (가이디드 필터 + 모폴로지)"""
import cv2
import numpy as np


def refine_alpha(bgra_image: np.ndarray) -> np.ndarray:
    """알파 채널을 정제하여 머리카락/엣지를 깔끔하게 처리"""
    alpha = bgra_image[:, :, 3].copy()
    rgb = bgra_image[:, :, :3]
    guide = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)

    # Step 1: 가이디드 필터 (엣지 보존 스무딩)
    alpha_f = alpha.astype(np.float32) / 255.0
    try:
        refined = cv2.ximgproc.guidedFilter(guide, alpha_f, radius=8, eps=1e-4)
    except AttributeError:
        # opencv-contrib 없을 시 bilateral filter fallback
        refined = cv2.bilateralFilter(alpha_f, 9, 75, 75)

    refined = np.clip(refined * 255, 0, 255).astype(np.uint8)

    # Step 2: 모폴로지 Close (머리카락 사이 작은 구멍 메우기)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    refined = cv2.morphologyEx(refined, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Step 3: 엣지 부분만 페더링
    edge = cv2.Canny(refined, 50, 150)
    edge_dilated = cv2.dilate(edge, kernel, iterations=2)
    blurred = cv2.GaussianBlur(refined, (5, 5), 0)
    refined = np.where(edge_dilated > 0, blurred, refined)

    bgra_image[:, :, 3] = refined
    return bgra_image
