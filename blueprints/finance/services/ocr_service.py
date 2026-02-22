import pytesseract
from PIL import Image
import io
import logging

class OCRService:
    @staticmethod
    def extract_text(file_stream):
        """
        Extracts text from an image file stream using Tesseract OCR.
        """
        try:
            image = Image.open(file_stream)
            # Optional: Add image preprocessing here (grayscale, thresholding) if needed
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            logging.error(f"OCR Extraction Error: {str(e)}")
            return ""

    @staticmethod
    def extract_text_from_bytes(file_bytes):
        """
        Extracts text from image bytes.
        """
        return OCRService.extract_text(io.BytesIO(file_bytes))
