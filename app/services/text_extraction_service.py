# app/services/text_extraction_service.py
from io import BytesIO
from typing import Optional

def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extracts text with multiple fallbacks:
    1) pdfplumber (pdfminer)
    2) PyMuPDF (fitz)
    3) PyPDF2
    Normalizes spaces at the end.
    """
    text = ""

    # 1) pdfplumber
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for p in pdf.pages:
                pages.append(p.extract_text() or "")
        text = "\n".join(pages)
    except Exception:
        text = ""

    # 2) PyMuPDF (fitz), if necessary
    if len((text or "").strip()) < 50:
        try:
            import fitz  # PyMuPDF
            pages = []
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                for page in doc:
                    pages.append(page.get_text("text") or "")
            text = "\n".join(pages)
        except Exception:
            pass

    # 3) PyPDF2, if we still didn't get anything useful
    if len((text or "").strip()) < 50:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(BytesIO(pdf_bytes))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages)
        except Exception:
            pass

    # final normalization
    for ch in ["\u00A0", "\u2007", "\u202F"]:
        text = text.replace(ch, " ")
    text = text.replace("\t", "    ")
    return text
