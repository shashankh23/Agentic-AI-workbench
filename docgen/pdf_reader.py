import pypdf

def extract_pdf_text(pdf_path: str) -> tuple[str, bool]:
    """
    Extracts text from a PDF. Returns (text, is_scanned).
    is_scanned=True means little/no embedded text was found — likely a scanned PDF.
    """
    reader = pypdf.PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() or ""

    is_scanned = len(full_text.strip()) < 50
    return full_text, is_scanned
