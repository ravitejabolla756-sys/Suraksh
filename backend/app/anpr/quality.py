"""Measure original pixels before enhancement; never mutate the source image."""
import math
import cv2
import numpy as np

from .contracts import ANPRConfig, PlateDetection, PlateQuality

PREPROCESSING_VERSION = "mild-crop-v1"


def assess(frame: np.ndarray, detection: PlateDetection, config: ANPRConfig) -> tuple[np.ndarray, PlateQuality]:
    h, w = frame.shape[:2]
    left, top, right, bottom = detection.bbox
    x1, y1 = max(0, math.floor(left)), max(0, math.floor(top))
    x2, y2 = min(w, math.ceil(right)), min(h, math.ceil(bottom))
    crop = frame[y1:max(y1, y2), x1:max(x1, x2)].copy()
    height, width = crop.shape[:2]
    visibility = max(0, min(w, right) - max(0, left)) * max(0, min(h, bottom) - max(0, top)) / ((right-left)*(bottom-top))
    if detection.visibility is not None:
        visibility = min(visibility, detection.visibility)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.size and crop.ndim == 3 else crop
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray.size else 0.0
    brightness = float(gray.mean()) if gray.size else 0.0
    contrast = float(gray.std()) if gray.size else 0.0
    angle = perspective = None
    reasons = []
    if detection.corners:
        corners = np.array(detection.corners, dtype=np.float32)
        if corners.shape != (4, 2) or not np.isfinite(corners).all() or not cv2.isContourConvex(corners):
            reasons.append("invalid_corners")
        else:
            tl, tr, br, bl = corners
            edges = [np.linalg.norm(tr-tl), np.linalg.norm(br-bl), np.linalg.norm(bl-tl), np.linalg.norm(br-tr)]
            angle = abs(math.degrees(math.atan2(float(tr[1]-tl[1]), float(tr[0]-tl[0]))))
            perspective = float(min(edges[0:2]) / max(max(edges[0:2]), 1) * min(edges[2:4]) / max(max(edges[2:4]), 1))
            if angle > config.maximum_angle_degrees or perspective < config.minimum_perspective_ratio:
                reasons.append("perspective")
            if any(not (left <= x <= right and top <= y <= bottom) for x, y in corners):
                reasons.append("corners_outside_crop")
    if width < config.minimum_crop_width or height < config.minimum_crop_height:
        reasons.append("small_crop")
    if blur < config.minimum_blur_variance:
        reasons.append("blur")
    if not config.minimum_brightness <= brightness <= config.maximum_brightness:
        reasons.append("exposure")
    if contrast < config.minimum_contrast:
        reasons.append("contrast")
    if visibility < config.minimum_visibility:
        reasons.append("visibility")
    if detection.confidence < config.minimum_detector_confidence:
        reasons.append("detector_confidence")
    score = min(1., width / max(config.minimum_crop_width*2, 1), height / max(config.minimum_crop_height*2, 1),
                blur / max(config.minimum_blur_variance*2, 1), contrast / max(config.minimum_contrast*2, 1), visibility, detection.confidence)
    return crop, PlateQuality(width, height, blur, brightness, contrast, detection.confidence, score,
                              visibility, angle, perspective, tuple(reasons))


def enhance(crop: np.ndarray, detection: PlateDetection, config: ANPRConfig) -> np.ndarray:
    result = crop.copy()
    if not config.enhancement:
        return result
    if detection.corners:
        origin = np.array([max(0, math.floor(detection.bbox[0])), max(0, math.floor(detection.bbox[1]))])
        corners = np.array(detection.corners, dtype=np.float32) - origin.astype(np.float32)
        h, w = crop.shape[:2]
        target = np.array([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]], dtype=np.float32)
        result = cv2.warpPerspective(result, cv2.getPerspectiveTransform(corners, target), (w, h))
    scale = min(2., 320 / max(result.shape[1], 1))
    if scale > 1:
        result = cv2.resize(result, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY) if result.ndim == 3 else result
    if gray.std() < 35:
        gray = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4)).apply(gray)
    # Modest denoising/sharpening only; original evidence is retained separately.
    filtered = cv2.bilateralFilter(gray, 3, 15, 15)
    return cv2.addWeighted(filtered, 1.2, cv2.GaussianBlur(filtered, (3, 3), 0), -.2, 0)
