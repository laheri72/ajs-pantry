"""Background job workers for receipt processing."""
import os
import logging
import time
from .services.parser_factory import ParserFactory

logger = logging.getLogger(__name__)


def _process_receipt_worker(file_path, mime_type, original_filename):
    """RQ Worker: Processes the receipt from a temporary file."""
    from app import app
    with app.app_context():
        started = time.monotonic()
        logger.info(
            "Receipt import job started: filename=%s mime_type=%s path=%s",
            original_filename,
            mime_type,
            file_path,
        )
        try:
            if not os.path.exists(file_path):
                logger.warning(
                    "Receipt temp file missing before processing: filename=%s path=%s duration=%.2fs",
                    original_filename,
                    file_path,
                    time.monotonic() - started,
                )
                return {'error': 'TEMP_FILE_MISSING'}

            with open(file_path, 'rb') as f:
                text = ParserFactory.get_text(f, mime_type)
                
            if not text or text == "ERROR_TESSERACT_NOT_FOUND":
                logger.warning(
                    "Receipt OCR failed: filename=%s mime_type=%s duration=%.2fs",
                    original_filename,
                    mime_type,
                    time.monotonic() - started,
                )
                return {'error': 'OCR_FAILED'}
            
            parser = ParserFactory.get_parser(text)
            receipt_data = parser.parse(text)
            
            if not receipt_data:
                logger.warning(
                    "Receipt parse failed: filename=%s parser=%s duration=%.2fs",
                    original_filename,
                    parser.__class__.__name__,
                    time.monotonic() - started,
                )
                return {'error': 'PARSE_FAILED'}
            
            data = receipt_data.to_dict()
            data['filename'] = original_filename
            logger.info(
                "Receipt import job completed: filename=%s parser=%s items=%s duration=%.2fs",
                original_filename,
                parser.__class__.__name__,
                len(data.get('items') or []),
                time.monotonic() - started,
            )
            return data
        except Exception as e:
            logger.exception(
                "Receipt import job crashed: filename=%s mime_type=%s duration=%.2fs",
                original_filename,
                mime_type,
                time.monotonic() - started,
            )
            return {'error': str(e)}
        finally:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info("Deleted receipt temp file: %s", file_path)
                except Exception:
                    logger.exception("Unable to delete receipt temp file: %s", file_path)
