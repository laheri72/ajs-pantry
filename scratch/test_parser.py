import sys
import os
import pdfplumber
import re
from datetime import datetime
import json

class ReceiptData:
    def __init__(self, bill_no=None, bill_date=None, shop_name=None, total_amount=0.0, items=None):
        self.bill_no = bill_no
        self.bill_date = bill_date
        self.shop_name = shop_name
        self.total_amount = total_amount
        self.items = items or []

class DMartParser:
    def parse(self, text):
        data = ReceiptData(shop_name='D-Mart (Avenue E-Commerce)')
        
        # 1. Extract Bill Number
        bill_no_match = re.search(r'(?:ORDER\s+NUMBER|Invoice\s+No)[\s:]*([A-Z0-9]+)', text, re.IGNORECASE)
        if bill_no_match:
            data.bill_no = bill_no_match.group(1)
        
        # 2. Extract Date
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
        new_item_pattern_5col = re.compile(
            r'(?m)^\s*(\d{6,14})\s*(.*?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})'
        )
        new_item_pattern_3col = re.compile(
            r'(?m)^\s*(\d{6,14})\s*(.*?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})'
        )
        
        matches = list(new_item_pattern_5col.finditer(text))
        col_type = 5
        if not matches:
            matches = list(new_item_pattern_3col.finditer(text))
            col_type = 3
            
        if matches:
            for match in matches:
                name_raw = match.group(2).strip()
                name = " ".join(name_raw.split())
                if not name or "CGST@" in name or "SGST@" in name or "TOTAL" in name.upper():
                    continue
                    
                cost_str = match.group(7) if col_type == 5 else match.group(5)
                data.items.append({
                    'name': name,
                    'quantity': match.group(3),
                    'cost': float(cost_str.replace(',', ''))
                })
        
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
        total_patterns = [
            r'Amount\s+([\d,]+\.\d+)',
            r'₹\s*([\d,]+\.\d+)\s+to\s+be\s+collected',
            r'Amt:\s*[\d\.]+\s+[\d\.]+\s+([\d\.]+)'
        ]
        
        for pattern in total_patterns:
            total_match = re.search(pattern, text, re.IGNORECASE)
            if total_match:
                data.total_amount = float(total_match.group(1).replace(',', ''))
                break
        
        if data.total_amount == 0 and data.items:
            data.total_amount = sum(item['cost'] for item in data.items)

        return data

def extract_text(pdf_path, out_file):
    out_file.write(f"Testing {pdf_path}\n")
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if text:
                full_text += text + "\n"
    
    out_file.write("--- EXTRACTED TEXT ---\n")
    out_file.write(full_text + "\n")
    out_file.write("----------------------\n")
    
    parser = DMartParser()
    data = parser.parse(full_text)
    
    out_file.write("\n--- PARSED DATA ---\n")
    out_file.write(f"Bill No: {data.bill_no}\n")
    out_file.write(f"Bill Date: {data.bill_date}\n")
    out_file.write(f"Total Amount: {data.total_amount}\n")
    out_file.write(f"Number of items: {len(data.items)}\n")
    out_file.write("Items:\n")
    for item in data.items:
        out_file.write(json.dumps(item) + "\n")

if __name__ == '__main__':
    with open('scratch/parser_output.txt', 'w', encoding='utf-8') as f:
        extract_text('invoice_224863459.pdf', f)
        extract_text('invoice_224882863.pdf', f)
        extract_text('invoice_226676683.pdf', f)
