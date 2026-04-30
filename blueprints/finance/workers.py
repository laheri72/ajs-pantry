"""Background job workers for receipt processing."""
import os
import logging
from .services.parser_factory import ParserFactory


def _process_receipt_worker(file_path, mime_type, original_filename):
    """RQ Worker: Processes the receipt from a temporary file."""
    from app import app
    with app.app_context():
        try:
            with open(file_path, 'rb') as f:
                text = ParserFactory.get_text(f, mime_type)
                
            if not text or text == "ERROR_TESSERACT_NOT_FOUND":
                return {'error': 'OCR_FAILED'}
            
            parser = ParserFactory.get_parser(text)
            receipt_data = parser.parse(text)
            
            if not receipt_data:
                return {'error': 'PARSE_FAILED'}
            
            data = receipt_data.to_dict()
            data['filename'] = original_filename
            return data
        except Exception as e:
            logging.error(f"Worker Error: {e}")
            return {'error': str(e)}
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
