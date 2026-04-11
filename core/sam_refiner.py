# core/sam_refiner.py
"""
SAM (Segment Anything Model) 기반 정밀 마스킹
YOLO가 찾은 bbox를 SAM에 전달하여 픽셀 단위 마스크 생성

지원 모델:
- MobileSAM (mobile_sam.pt) — 경량, 빠름
- FastSAM (FastSAM-s.pt) — YOLO 기반, 가벼움
- SAM (sam_vit_b.pt) — 원본, 무거움

editor_models/ 디렉토리에 모델 파일을 넣으면 자동 감지
"""
import os
import numpy as np
import cv2


def find_sam_model(models_dir: str) -> tuple:
    """editor_models/에서 SAM 모델 자동 감지 → (path, type)"""
    if not os.path.isdir(models_dir):
        return None, None

    # 우선순위: MobileSAM > FastSAM > SAM
    priority = [
        ('mobile_sam', 'mobile_sam'),
        ('FastSAM', 'fast_sam'),
        ('sam_vit_b', 'sam'),
        ('sam_vit_l', 'sam'),
        ('sam_vit_h', 'sam'),
    ]

    # YOLO 모델 제외 키워드
    yolo_keywords = ['yolo', 'nsfw', 'detect', 'censor']

    # 1차: 키워드 매칭
    for fname in os.listdir(models_dir):
        flow = fname.lower()
        if not flow.endswith(('.pt', '.pth', '.onnx')):
            continue
        if any(yk in flow for yk in yolo_keywords):
            continue
        for keyword, sam_type in priority:
            if keyword.lower() in flow:
                return os.path.join(models_dir, fname), sam_type

    # 2차: 'sam'이 포함된 모든 파일 (폴백)
    for fname in os.listdir(models_dir):
        flow = fname.lower()
        if not flow.endswith(('.pt', '.pth', '.onnx')):
            continue
        if any(yk in flow for yk in yolo_keywords):
            continue
        if 'sam' in flow:
            sam_type = 'mobile_sam' if 'mobile' in flow else 'sam'
            return os.path.join(models_dir, fname), sam_type

    return None, None


def refine_boxes_with_sam(image: np.ndarray, boxes: list, models_dir: str,
                          sam_model_path: str = None, sam_type: str = None) -> np.ndarray:
    """
    YOLO bbox 목록을 SAM으로 정밀 마스킹

    Args:
        image: BGR numpy 이미지
        boxes: [(x1, y1, x2, y2), ...] YOLO 검출 박스
        models_dir: editor_models/ 경로
        sam_model_path: SAM 모델 파일 경로 (None이면 자동 감지)
        sam_type: 'mobile_sam', 'fast_sam', 'sam'

    Returns:
        combined_mask: uint8 마스크 (0 or 255)
    """
    h, w = image.shape[:2]
    combined_mask = np.zeros((h, w), dtype=np.uint8)

    if not boxes:
        return combined_mask

    # SAM 모델 찾기
    if sam_model_path is None:
        sam_model_path, sam_type = find_sam_model(models_dir)

    if sam_model_path is None or not os.path.exists(sam_model_path):
        print(f"[SAM] No SAM model found in {models_dir}")
        print(f"[SAM] Files: {os.listdir(models_dir) if os.path.isdir(models_dir) else 'dir not found'}")
        print("[SAM] Falling back to bbox mask")
        for (x1, y1, x2, y2) in boxes:
            combined_mask[y1:y2, x1:x2] = 255
        return combined_mask

    print(f"[SAM] Found model: {sam_type} → {sam_model_path}")
    print(f"[SAM] Processing {len(boxes)} boxes...")

    try:
        if sam_type == 'fast_sam':
            return _refine_with_fastsam(image, boxes, sam_model_path, combined_mask)
        else:
            return _refine_with_sam(image, boxes, sam_model_path, sam_type, combined_mask)
    except Exception as e:
        import traceback
        print(f"[SAM] Error: {e}")
        traceback.print_exc()
        for (x1, y1, x2, y2) in boxes:
            combined_mask[y1:y2, x1:x2] = 255
        return combined_mask


def _refine_with_sam(image: np.ndarray, boxes: list, model_path: str,
                     sam_type: str, mask: np.ndarray) -> np.ndarray:
    """MobileSAM / SAM으로 정밀 마스킹"""
    import torch

    # SAM 라이브러리 로드 (여러 패키지 시도)
    SamPredictor = None
    sam_model_registry = None
    model_type = 'vit_b'

    _mobile_err = None
    if sam_type == 'mobile_sam':
        try:
            from mobile_sam import sam_model_registry, SamPredictor
            model_type = 'vit_t'
            print("[SAM] Using mobile_sam package (vit_t)")
        except ImportError as ie:
            _mobile_err = ie
            print(f"[SAM] mobile_sam import failed: {ie}")

    if SamPredictor is None:
        try:
            from segment_anything import sam_model_registry, SamPredictor
            if 'vit_h' in model_path.lower(): model_type = 'vit_h'
            elif 'vit_l' in model_path.lower(): model_type = 'vit_l'
            elif 'vit_t' in model_path.lower() or 'mobile' in model_path.lower(): model_type = 'vit_t'
            else: model_type = 'vit_b'
            print(f"[SAM] Using segment_anything package ({model_type})")
        except ImportError as ie2:
            print(f"[SAM] Neither mobile_sam nor segment_anything installed")
            print(f"[SAM] mobile_sam error: {_mobile_err}")
            print(f"[SAM] segment_anything error: {ie2}")
            for (x1, y1, x2, y2) in boxes:
                mask[y1:y2, x1:x2] = 255
            return mask

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    sam = sam_model_registry[model_type](checkpoint=model_path)
    sam.to(device)
    predictor = SamPredictor(sam)

    # RGB로 변환 후 이미지 설정
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    predictor.set_image(rgb)

    for (x1, y1, x2, y2) in boxes:
        box = np.array([x1, y1, x2, y2])
        masks, scores, _ = predictor.predict(
            box=box,
            multimask_output=True,
        )
        # 가장 높은 스코어 마스크 선택
        best_idx = np.argmax(scores)
        seg_mask = masks[best_idx].astype(np.uint8) * 255
        mask = np.maximum(mask, seg_mask)

    return mask


def _refine_with_fastsam(image: np.ndarray, boxes: list,
                         model_path: str, mask: np.ndarray) -> np.ndarray:
    """FastSAM으로 정밀 마스킹"""
    from ultralytics import YOLO as FastSAMModel
    h, w = image.shape[:2]

    model = FastSAMModel(model_path)
    results = model(image, retina_masks=True, conf=0.4, iou=0.7)

    if not results or results[0].masks is None:
        for (x1, y1, x2, y2) in boxes:
            mask[y1:y2, x1:x2] = 255
        return mask

    all_masks = results[0].masks.data.cpu().numpy()

    for (bx1, by1, bx2, by2) in boxes:
        best_iou = 0
        best_mask = None

        for seg in all_masks:
            seg_resized = cv2.resize(seg.astype(np.float32), (w, h))
            # bbox 영역과의 IoU 계산
            box_mask = np.zeros((h, w), dtype=np.float32)
            box_mask[by1:by2, bx1:bx2] = 1.0
            intersection = (seg_resized > 0.5) & (box_mask > 0.5)
            union = (seg_resized > 0.5) | (box_mask > 0.5)
            iou = intersection.sum() / max(union.sum(), 1)

            if iou > best_iou:
                best_iou = iou
                best_mask = seg_resized

        if best_mask is not None and best_iou > 0.1:
            mask[best_mask > 0.5] = 255
        else:
            # fallback: bbox만
            mask[by1:by2, bx1:bx2] = 255

    return mask
