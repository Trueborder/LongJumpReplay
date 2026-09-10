from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np


def shadow_like_mask(current_bgr: np.ndarray, background_bgr: np.ndarray) -> np.ndarray:
    """Identify illumination-only darkening while preserving hard object edges."""
    current_hsv = cv2.cvtColor(current_bgr, cv2.COLOR_BGR2HSV)
    background_hsv = cv2.cvtColor(background_bgr, cv2.COLOR_BGR2HSV)
    current_value = current_hsv[:, :, 2].astype(np.float32)
    background_value = background_hsv[:, :, 2].astype(np.float32)
    value_ratio = (current_value + 1.0) / (background_value + 1.0)
    value_drop = background_value - current_value
    saturation_delta = cv2.absdiff(current_hsv[:, :, 1], background_hsv[:, :, 1])
    hue_delta = cv2.absdiff(current_hsv[:, :, 0], background_hsv[:, :, 0])
    hue_delta = np.minimum(hue_delta, 180 - hue_delta)
    both_neutral = (current_hsv[:, :, 1] < 35) & (background_hsv[:, :, 1] < 35)
    same_colour = (saturation_delta < 34) & ((hue_delta < 14) | both_neutral)
    shadow = (value_drop >= 8) & (value_ratio >= .43) & (value_ratio <= .96) & same_colour

    return shadow


def foreground_motion_mask(
    current_bgr: np.ndarray,
    reference_bgrs: Sequence[np.ndarray],
    search_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return local object motion and a diagnostic shadow mask."""
    references = [reference for reference in reference_bgrs if reference is not None and reference.shape == current_bgr.shape]
    if not references:
        empty = np.zeros(current_bgr.shape[:2], dtype=np.uint8)
        return empty, empty.astype(bool)
    background = np.median(np.stack(references, axis=0), axis=0).astype(np.uint8)
    current_gray = cv2.cvtColor(current_bgr, cv2.COLOR_BGR2GRAY)
    background_gray = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    motion = cv2.absdiff(current_gray, background_gray).astype(np.float32)
    motion -= float(np.median(motion))
    np.maximum(motion, 0, out=motion)
    positive = motion[motion > 0]
    if positive.size == 0:
        empty = np.zeros(motion.shape, dtype=np.uint8)
        return empty, empty.astype(bool)
    threshold = max(9.0, float(np.percentile(positive, 82)))
    shadow = shadow_like_mask(current_bgr, background) | shadow_like_mask(background, current_bgr)
    foreground = (motion >= threshold) & ~shadow
    if search_mask is not None:
        foreground &= search_mask > 0
    mask = foreground.astype(np.uint8) * 255
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask, shadow
