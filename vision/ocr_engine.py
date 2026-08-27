from paddleocr import PaddleOCR
import logging

# Suppress verbose paddle logging cleanly
logging.getLogger("ppocr").setLevel(logging.ERROR)

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            # Modern PaddleOCR initialization
            _ocr_engine = PaddleOCR(use_angle_cls=True, lang='en')
        except TypeError:
            # Fallback for older parameter variants
            _ocr_engine = PaddleOCR(lang='en')
    return _ocr_engine

def run_ocr(image_path: str) -> list:
    """
    Runs PaddleOCR on an image.
    Returns: [{"text": str, "confidence": float, "bbox": [[x,y],...]}]
    """
    engine = get_ocr_engine()
    result = engine.ocr(image_path, cls=True)

    blocks = []
    if result and result[0]:
        for line in result[0]:
            bbox, (text, confidence) = line
            blocks.append({
                "text": text,
                "confidence": float(confidence),  # Normalizes 0.0 - 1.0 scale
                "bbox": bbox
            })
    return blocks