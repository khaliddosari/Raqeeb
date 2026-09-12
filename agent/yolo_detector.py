"""YOLO is responsible for detection ONLY. It has no knowledge of incidents, reports,
authorities, or Gemini. It takes an image and returns a class + confidence, full stop.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from agent.config import settings
from agent.schemas import DetectionResult


class NoDetectionError(Exception):
    """Raised when YOLO finds nothing above the confidence threshold."""


class YoloDetector:
    def __init__(self, weights_path: str | None = None, confidence_threshold: float | None = None):
        self.weights_path = weights_path or settings.yolo_weights_path
        self.confidence_threshold = (
            confidence_threshold if confidence_threshold is not None else settings.yolo_confidence_threshold
        )
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from ultralytics import YOLO  # imported lazily so the rest of the app can

            if not Path(self.weights_path).exists():
                raise FileNotFoundError(f"YOLO weights not found at {self.weights_path}")
            self._model = YOLO(self.weights_path)
        return self._model

    @staticmethod
    def annotated_path_for(image_path: str) -> Path:
        """Where the boxed render of image_path lives. Derived by convention rather than
        stored, so nothing downstream has to thread an extra path around."""
        p = Path(image_path)
        return p.with_name(f"{p.stem}_annotated.png")

    def detect(self, image_path: str, annotate: bool = False) -> DetectionResult:
        """Runs inference and returns the single highest-confidence detection.

        Raises NoDetectionError if nothing clears the confidence threshold. Never
        called again for the same incident once a DetectionResult is stored.

        annotate=True additionally writes a boxed render next to the source image, from
        this same inference pass. It is a rendering side effect only: the returned
        DetectionResult is identical either way, and a failure to write never fails the
        detection.
        """
        # device="cpu" pinned deliberately -- this only needs to run once per incident,
        # and pinning avoids environments where torch detects a GPU but the installed
        # CUDA build doesn't actually match the driver/hardware (kernel image errors).
        results = self.model.predict(image_path, verbose=False, device="cpu")
        r = results[0]

        if annotate:
            try:
                import cv2

                cv2.imwrite(str(self.annotated_path_for(image_path)), r.plot())
            except Exception:
                pass

        best_cls: int | None = None
        best_conf = 0.0

        obb = getattr(r, "obb", None)
        if obb is not None and obb.cls.numel() > 0:
            for cls, conf in zip(obb.cls.tolist(), obb.conf.tolist()):
                if conf > best_conf:
                    best_cls, best_conf = int(cls), float(conf)
        else:
            boxes = getattr(r, "boxes", None)
            if boxes is not None and boxes.cls.numel() > 0:
                for cls, conf in zip(boxes.cls.tolist(), boxes.conf.tolist()):
                    if conf > best_conf:
                        best_cls, best_conf = int(cls), float(conf)

        if best_cls is None or best_conf < self.confidence_threshold:
            raise NoDetectionError(f"No detection above threshold {self.confidence_threshold}")

        return DetectionResult(detected_class=self.model.names[best_cls], confidence=round(best_conf, 4))


@lru_cache
def get_detector() -> YoloDetector:
    return YoloDetector()
