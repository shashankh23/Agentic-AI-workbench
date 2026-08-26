from PIL import Image
from vision.ocr_engine import run_ocr
from vision.vision import analyze_image  # your existing vision model call
import os
import uuid

CONFIDENCE_THRESHOLD = 0.85

def crop_and_save(image_path: str, bbox: list, output_dir: str) -> str:
    """Crops a region from the image based on OCR bounding box and saves it."""
    img = Image.open(image_path)
    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)

    cropped = img.crop((left, top, right, bottom))
    crop_path = os.path.join(output_dir, f"crop_{uuid.uuid4().hex[:8]}.png")
    cropped.save(crop_path)
    return crop_path

def process_document_image(image_path: str) -> dict:
    """
    Runs OCR on an image, escalating low-confidence blocks to the vision model.
    Returns {"full_text": str, "escalated_blocks": int, "total_blocks": int}
    """
    blocks = run_ocr(image_path)
    crop_dir = os.path.join(os.getcwd(), "ocr_crops")
    os.makedirs(crop_dir, exist_ok=True)

    final_text_parts = []
    escalated_count = 0

    for block in blocks:
        if block["confidence"] >= CONFIDENCE_THRESHOLD:
            final_text_parts.append(block["text"])
        else:
            # Low confidence — isolate this crop and hand it to the vision model
            crop_path = crop_and_save(image_path, block["bbox"], crop_dir)
            vision_result = analyze_image(
                "Read and transcribe the text in this image precisely.",
                crop_path
            )
            final_text_parts.append(vision_result)
            escalated_count += 1
            os.remove(crop_path)  # cleanup

    return {
        "full_text": "\n".join(final_text_parts),
        "escalated_blocks": escalated_count,
        "total_blocks": len(blocks)
    }
