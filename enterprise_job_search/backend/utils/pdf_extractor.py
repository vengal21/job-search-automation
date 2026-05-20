import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file. 
    Attempts standard text extraction first. If a page appears to be a scanned image (very little text),
    it falls back to OCR using Tesseract.
    """
    text_content = []
    
    try:
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            
            # If the page yields very little text, it might be an image/scan
            if len(text) < 50:
                logger.info(f"Page {page_num} seems scanned. Using OCR.")
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                # Note: Tesseract must be installed on the system (e.g. apt-get install tesseract-ocr)
                ocr_text = pytesseract.image_to_string(img)
                text_content.append(ocr_text)
            else:
                text_content.append(text)
                
        return "\n".join(text_content)
    except Exception as e:
        logger.error(f"Error extracting PDF: {e}")
        raise
