import re
from datetime import datetime
import logging

class ReceiptData:
    def __init__(self, bill_no=None, bill_date=None, shop_name=None, total_amount=0.0, items=None):
        self.bill_no = bill_no
        self.bill_date = bill_date
        self.shop_name = shop_name
        self.total_amount = total_amount
        self.items = items or []

    def to_dict(self):
        return {
            'bill_no': self.bill_no,
            'bill_date': self.bill_date,
            'shop_name': self.shop_name,
            'total_amount': self.total_amount,
            'items': self.items
        }

class BaseParser:
    def parse(self, text):
        raise NotImplementedError("Subclasses must implement parse()")

class DMartParser(BaseParser):
    def parse(self, text):
        data = ReceiptData(shop_name='D-Mart (Avenue E-Commerce)')
        
        # 1. Extract Bill Number (Handles "ORDER NUMBER:" or "Invoice No:")
        bill_no_match = re.search(r'(?:ORDER\s+NUMBER|Invoice\s+No)[\s:]*([A-Z0-9]+)', text, re.IGNORECASE)
        if bill_no_match:
            data.bill_no = bill_no_match.group(1)
        
        # 2. Extract Date (Handles "INVOICE DATE:" or "ORDER DATE:")
        date_match = re.search(r'(?:INVOICE|ORDER)\s+DATE[\s:]*(\d{2}/\d{2}/\d{2,4})', text, re.IGNORECASE)
        if date_match:
            try:
                raw_date = date_match.group(1)
                fmt = '%d/%m/%y' if len(raw_date.split('/')[-1]) == 2 else '%d/%m/%Y'
                dt_obj = datetime.strptime(raw_date, fmt)
                data.bill_date = dt_obj.strftime('%Y-%m-%d')
            except:
                pass

        # 3. Extract Items
        # New Format Strategy: Look for HSN (6-10 digits) followed by Particulars and the 5 numeric columns.
        # We use re.finditer to find these blocks across the whole text.
        # Pattern: [HSN] [MashedName] [Qty] [Rate] [Value] [Discount] [NetValue]
        # Note: We allow newlines in the name section and handle the "no space" after HSN.
        new_item_pattern = re.compile(
            r'(\d{6,10})\s*(.*?)\s+(\d+(?:\.\d+)?)\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})', 
            re.DOTALL
        )
        
        matches = list(new_item_pattern.finditer(text))
        if matches:
            for match in matches:
                name_raw = match.group(2).strip()
                # Clean up multi-line names and remove extra spaces
                name = " ".join(name_raw.split())
                
                # Filter out tax headers or summary lines that might match the digit pattern
                if not name or "CGST@" in name or "SGST@" in name or "TOTAL" in name.upper():
                    continue
                    
                data.items.append({
                    'name': name,
                    'quantity': match.group(3),
                    'cost': float(match.group(7))
                })
        
        # Fallback to Old Format if no items found with the new pattern
        if not data.items:
            old_item_pattern = re.compile(r'^(\d+)\.\s+(\d{4,10})\s+(\d+)\s+(.*?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)', re.MULTILINE)
            matches = old_item_pattern.findall(text)
            for m in matches:
                try:
                    data.items.append({
                        'name': str(m[3]).strip(),
                        'quantity': str(m[4]),
                        'cost': float(m[6].replace(',', ''))
                    })
                except:
                    continue

        # 4. Extract Total
        # Look for "Amount [total]" or "₹[total] to be collected"
        total_patterns = [
            r'Amount\s+([\d,]+\.\d+)',
            r'₹\s*([\d,]+\.\d+)\s+to\s+be\s+collected',
            r'Amt:\s*[\d\.]+\s+[\d\.]+\s+([\d\.]+)'  # Summary line: Items:11 Qty:13 Amt: ... [Total]
        ]
        
        for pattern in total_patterns:
            total_match = re.search(pattern, text, re.IGNORECASE)
            if total_match:
                data.total_amount = float(total_match.group(1).replace(',', ''))
                break
        
        if data.total_amount == 0 and data.items:
            data.total_amount = sum(item['cost'] for item in data.items)

        return data

class GenericParser(BaseParser):
    def parse(self, text):
        data = ReceiptData(shop_name='Unknown Store')
        
        # Try to find something that looks like a total
        # Look for "Total", "Net Amount", "Grand Total"
        total_patterns = [
            r'(?:TOTAL|GRAND\s+TOTAL|NET\s+AMOUNT|AMOUNT\s+DUE)[\s:]+([\d,]+\.\d{2})',
            r'RS\.?\s*([\d,]+\.\d{2})',
            r'TOTAL\s+PAYABLE[\s:]+([\d,]+\.\d{2})'
        ]
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data.total_amount = float(match.group(1).replace(',', ''))
                break

        # Try to find a date
        date_patterns = [
            r'(\d{2}/\d{2}/\d{4})',
            r'(\d{2}-\d{2}-\d{4})',
            r'(\d{2}/\d{2}/\d{2})',
            r'(\d{2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4})'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    # Very basic date parsing, could be improved with dateutil
                    raw_date = match.group(1)
                    # This is just a placeholder for more robust parsing
                    data.bill_date = raw_date 
                    break
                except:
                    pass

        return data
