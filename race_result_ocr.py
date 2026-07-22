import os
import threading

import cv2
import numpy as np
import yaml

from app_resources import get_app_dir


TITLE_CROP = (0.02, 0.17, 0.25, 0.265)
OCR_HEIGHT = 48
OCR_MAX_WIDTH = 320


class ChallengeResultOCR:
    """Small, lazy OpenCV-DNN OCR verifier for the large result title."""

    def __init__(self, log_func=None):
        self.log = log_func or (lambda *_args, **_kwargs: None)
        self.net = None
        self.ort_session = None
        self.chars = None
        self.load_error = None
        self._lock = threading.Lock()

    def _model_paths(self):
        root = os.path.join(get_app_dir(), "models", "race_ocr")
        return (
            os.path.join(root, "recognition.onnx"),
            os.path.join(root, "recognition.yml"),
        )

    def ensure_loaded(self):
        if (self.net is not None or self.ort_session is not None) and self.chars is not None:
            return True
        if self.load_error is not None:
            return False
        with self._lock:
            if (self.net is not None or self.ort_session is not None) and self.chars is not None:
                return True
            try:
                model_path, config_path = self._model_paths()
                try:
                    cv_major = int(str(cv2.__version__).split(".", 1)[0])
                    if cv_major < 5:
                        raise RuntimeError("OpenCV 4.x requires ONNX Runtime for this OCR model")
                    self.net = cv2.dnn.readNetFromONNX(model_path)
                except Exception:
                    # OpenCV 4.x cannot import the dynamic Transpose used by
                    # this PP-OCRv6 model.  Release builds use this CPU fallback.
                    import onnxruntime as ort

                    options = ort.SessionOptions()
                    options.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)
                    options.inter_op_num_threads = 1
                    self.ort_session = ort.InferenceSession(
                        model_path,
                        sess_options=options,
                        providers=["CPUExecutionProvider"],
                    )
                with open(config_path, "r", encoding="utf-8") as stream:
                    config = yaml.safe_load(stream)
                self.chars = config["PostProcess"]["character_dict"]
                return True
            except Exception as exc:
                self.load_error = str(exc)
                self.net = None
                self.ort_session = None
                self.chars = None
                self.log(f"[ChallengeOCR] load failed: {exc}", level="WARN", frontend=False)
                return False

    @staticmethod
    def _crop_title(image):
        if image is None or image.size == 0:
            return None
        height, width = image.shape[:2]
        x1, y1, x2, y2 = TITLE_CROP
        crop = image[
            max(0, int(height * y1)):min(height, int(height * y2)),
            max(0, int(width * x1)):min(width, int(width * x2)),
        ]
        return crop if crop.size else None

    @staticmethod
    def _preprocess(crop):
        height, width = crop.shape[:2]
        target_width = min(OCR_MAX_WIDTH, max(4, int(width * OCR_HEIGHT / max(1, height))))
        target_width = max(4, (target_width // 4) * 4)
        resized = cv2.resize(crop, (target_width, OCR_HEIGHT), interpolation=cv2.INTER_LINEAR)
        tensor = resized.astype(np.float32) / 255.0
        tensor = (tensor - 0.5) / 0.5
        return np.ascontiguousarray(tensor.transpose(2, 0, 1)[None, ...], dtype=np.float32)

    def _decode(self, prediction):
        if prediction.ndim == 3:
            prediction = prediction[0]
        text = []
        confidences = []
        last_index = -1
        for row in prediction:
            index = int(np.argmax(row))
            if index != last_index and index != 0 and index - 1 < len(self.chars):
                text.append(self.chars[index - 1])
                confidences.append(float(row[index]))
            last_index = index
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return "".join(text), confidence

    def recognize(self, screen_bgr):
        if not self.ensure_loaded():
            return {"status": None, "text": "", "confidence": 0.0}
        crop = self._crop_title(screen_bgr)
        if crop is None:
            return {"status": None, "text": "", "confidence": 0.0}
        try:
            tensor = self._preprocess(crop)
            if self.net is not None:
                self.net.setInput(tensor)
                prediction = self.net.forward()
            else:
                input_name = self.ort_session.get_inputs()[0].name
                prediction = self.ort_session.run(None, {input_name: tensor})[0]
            text, confidence = self._decode(prediction)
            normalized = "".join(text.split()).replace("!", "").replace("！", "")
            status = None
            if "挑战完成" in normalized or "完成" in normalized:
                status = "success"
            elif "挑战失败" in normalized or "失败" in normalized:
                status = "failed"
            return {"status": status, "text": text, "confidence": confidence}
        except Exception as exc:
            self.log(f"[ChallengeOCR] inference failed: {exc}", level="WARN", frontend=False)
            return {"status": None, "text": "", "confidence": 0.0}
