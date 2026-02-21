import pdfplumber
import re
from datetime import datetime

class PDFParserService:
    @staticmethod
    def parse_dmart_invoice(file_stream):
        """
        Parses a digitally generated D-Mart PDF invoice with high robustness.
        """
        data = {
            'bill_no': None,
            'bill_date': None,
            'shop_name': 'D-Mart (Avenue E-Commerce)',
            'total_amount': 0.0,
            'items': []
        }

        with pdfplumber.open(file_stream) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"

            # 1. Extract Header Info
            # Order Number: Look for digits after "ORDER NUMBER:"
            order_match = re.search(r'ORDER\s+NUMBER:\s*(\d+)', full_text, re.IGNORECASE)
            if order_match:
                data['bill_no'] = order_match.group(1)
            
            # Invoice Date: Look for dd/mm/yy near "INVOICE DATE:"
            # Handles possible newlines or extra spaces
            date_match = re.search(r'INVOICE\s+DATE:\s*(\d{2}/\d{2}/\d{2,4})', full_text, re.IGNORECASE)
            if date_match:
                try:
                    raw_date = date_match.group(1)
                    # Handle both 2-digit and 4-digit years
                    fmt = '%d/%m/%y' if len(raw_date.split('/')[-1]) == 2 else '%d/%m/%Y'
                    dt_obj = datetime.strptime(raw_date, fmt)
                    data['bill_date'] = dt_obj.strftime('%Y-%m-%d')
                except:
                    pass

            # 2. Extract Items using robust Regex on text lines
            # D-Mart Line Pattern: [SR] [HSN] [TAX] [NAME] [QTY] [RATE] [VALUE]
            # Example: "1. 21069099 3 Balaji Aloo Sev 400Gm 1.0 75.00 75.00"
            item_pattern = re.compile(r'^(\d+)\.\s+(\d{4,10})\s+(\d+)\s+(.*?)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+([\d,]+\.\d+)', re.MULTILINE)
            
            matches = item_pattern.findall(full_text)
            for m in matches:
                try:
                    # m[3] is name, m[4] is qty, m[6] is value
                    name = str(m[3]).strip()
                    qty = str(m[4]).strip()
                    val = str(m[6]).replace(',', '')
                    
                    data['items'].append({
                        'name': name,
                        'quantity': qty,
                        'cost': float(val)
                    })
                except (ValueError, IndexError):
                    continue

            # 3. Extract Totals
            # Look for the final amount paid
            amount_match = re.findall(r'Amount\s+([\d,]+\.\d+)', full_text, re.IGNORECASE)
            if amount_match:
                data['total_amount'] = float(amount_match[-1].replace(',', ''))
            
            # If regex total is 0, fallback to items sum
            if data['total_amount'] == 0 and data['items']:
                data['total_amount'] = sum(item['cost'] for item in data['items'])

        return data
