from __future__ import annotations

import cv2
import numpy as np
import pytest


@pytest.fixture
def jpeg_frame():
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    cv2.rectangle(frame, (30, 20), (120, 70), (0, 180, 255), -1)
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    return data.tobytes(), frame
