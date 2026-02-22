import logging
import io
from .pdf_service import PDFService
from .ocr_service import OCRService
from .receipt_parser import DMartParser, GenericParser

class ParserFactory:
    @staticmethod
    def get_text(file_stream, mime_type):
        """
        Detects file type and extracts text using PDF or OCR service.
        """
        if mime_type == 'application/pdf':
            return PDFService.extract_text(file_stream)
        elif mime_type.startswith('image/'):
            return OCRService.extract_text(file_stream)
        else:
            logging.error(f"Unsupported MIME type: {mime_type}")
            return ""

    @staticmethod
    def get_parser(text):
        """
        Detects the store template based on text content and returns the appropriate parser.
        """
        text_upper = text.upper()
        
        # D-Mart detection
        if "AVENUE E-COMMERCE" in text_upper or "DMART" in text_upper or "ORDER NUMBER" in text_upper:
            return DMartParser()
        
        # Add more store detections here
        # elif "RELIANCE" in text_upper:
        #     return RelianceParser()
            
        return GenericParser()

    @staticmethod
    def process_receipt(file_stream, mime_type):
        """
        Full pipeline: Extract Text -> Detect Parser -> Parse Data
        """
        text = ParserFactory.get_text(file_stream, mime_type)
        if not text:
            return None
        
        parser = ParserFactory.get_parser(text)
        receipt_data = parser.parse(text)
        return receipt_data
