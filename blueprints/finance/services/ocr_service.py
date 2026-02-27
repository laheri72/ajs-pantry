import pytesseract
from PIL import Image, ImageOps, ImageEnhance
import io
import os
import logging

# Check for TESSERACT_CMD in environment variables
tesseract_cmd = os.getenv('TESSERACT_CMD')
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

class OCRService:
    @staticmethod
    def extract_text(file_stream):
        """
        Extracts text from an image file stream using Tesseract OCR with balanced preprocessing.
        """
        try:
            image = Image.open(file_stream)
            
            # 1. Convert to grayscale
            image = ImageOps.grayscale(image)
            
            # 2. Balanced contrast enhancement
            image = ImageEnhance.Contrast(image).enhance(1.8)
            
            # 3. Resize only if small
            if image.width < 1500:
                scale = 2000 / image.width
                new_size = (int(image.width * scale), int(image.height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            # 4. Use psm 3 for standard layout, fallback to 6
            text = pytesseract.image_to_string(image, config='--psm 3')
            
            if len(text.strip()) < 20:
                text = pytesseract.image_to_string(image, config='--psm 6')
                
            return text
        except pytesseract.TesseractNotFoundError:
            logging.error("OCR Error: Tesseract binary not found. Please install Tesseract OCR on the system.")
            return "ERROR_TESSERACT_NOT_FOUND"
        except Exception as e:
            logging.error(f"OCR Extraction Error: {str(e)}")
            return ""

    @staticmethod
    def extract_text_from_bytes(file_bytes):
        """
        Extracts text from image bytes.
        """
        return OCRService.extract_text(io.BytesIO(file_bytes))
