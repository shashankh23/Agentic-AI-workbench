from paddleocr import PaddleOCR

# Initialize once, reused across calls (loading the model repeatedly is slow)
_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
    return _ocr_engine

def run_ocr(image_path: str) -> list:
    """
    Runs PaddleOCR on an image. Returns a list of blocks:
    [{"text": str, "confidence": float, "bbox": [[x,y],...]}]
    """
    engine = get_ocr_engine()
    result = engine.ocr(image_path, cls=True)

    blocks = []
    if result and result[0]:
        for line in result[0]:
            bbox, (text, confidence) = line
            blocks.append({
                "text": text,
                "confidence": confidence,  # 0.0 to 1.0
                "bbox": bbox
            })
    return blocks