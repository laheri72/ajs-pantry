import pdfplumber
import io
import logging

class PDFService:
    @staticmethod
    def extract_text(file_stream):
        """
        Extracts text from a PDF file stream using pdfplumber.
        """
        try:
            full_text = ""
            with pdfplumber.open(file_stream) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
            return full_text
        except Exception as e:
            logging.error(f"PDF Extraction Error: {str(e)}")
            return ""

    @staticmethod
    def extract_text_from_bytes(file_bytes):
        """
        Extracts text from PDF bytes.
        """
        return PDFService.extract_text(io.BytesIO(file_bytes))
