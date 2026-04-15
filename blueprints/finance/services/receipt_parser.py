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
        # Self-Pickup / New Tax Invoice Format checks
        # Format A: 5 numeric columns (Qty Rate Value Discount NetValue)
        new_item_pattern_5col = re.compile(
            r'(?m)^\s*(\d{6,14})\s*(.*?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})'
        )
        # Format B: 3 numeric columns (Qty Rate Value)
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
                # Clean up multi-line names and remove extra spaces
                name = " ".join(name_raw.split())
                
                # Filter out tax headers or summary lines that might match the digit pattern
                if not name or "CGST@" in name or "SGST@" in name or "TOTAL" in name.upper():
                    continue
                    
                cost_str = match.group(7) if col_type == 5 else match.group(5)
                data.items.append({
                    'name': name,
                    'quantity': match.group(3),
                    'cost': float(cost_str.replace(',', ''))
                })
        
        # Fallback to Old Format if no items found with the new pattern
        if not data.items:
            # Allow optional leading whitespace before the item number
            old_item_pattern = re.compile(r'^\s*(\d+)\.\s+(\d{4,10})\s+(\d+)\s+(.*?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)', re.MULTILINE)
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

class BlinkitParser(BaseParser):
    def parse(self, text):
        data = ReceiptData(shop_name='Blinkit (Blink Commerce)')
        
        # 1. Extract Order ID / Bill No
        # Look for "Order Id : 402613975" or "Invoice Number : C20632T230216450"
        bill_no_match = re.search(r'(?:Order\s+Id|Invoice\s+Number)[\s:]+([A-Z0-9]+)', text, re.IGNORECASE)
        if bill_no_match:
            data.bill_no = bill_no_match.group(1)
        
        # 2. Extract Date
        # Look for "Invoice Date : 29-Nov-2023" or "Invoice : 27-Mar-2026"
        date_match = re.search(r'Invoice(?:\s+Date)?\s*:\s*(\d{2}-[a-zA-Z]{3}-\d{4})', text, re.IGNORECASE)
        if date_match:
            try:
                dt_obj = datetime.strptime(date_match.group(1), '%d-%b-%Y')
                data.bill_date = dt_obj.strftime('%Y-%m-%d')
            except:
                pass

        # 3. Extract Items
        # Table format: Sr. no | UPC | Item Description | MRP | Discount | Qty | Taxable Value | ... | Total
        # Example: 1 | 890... | Prega News ... | 60.00 | 0.50 | 2 | 106.25 | ... | 119.00
        # We look for lines starting with a serial number, optional trailing UPC, name, and column values
        item_pattern = re.compile(
            r'^\s*(\d+)\s+([\d\-]*)\s+(.*?)\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+)\s+(\d+\.\d{2}).*?(\d+\.\d{2})\s*$',
            re.MULTILINE
        )
        
        matches = item_pattern.findall(text)
        for m in matches:
            try:
                data.items.append({
                    'name': m[2].strip(),
                    'quantity': m[5],
                    'cost': float(m[7])
                })
            except:
                continue

        # 4. Extract Delivery/Handling Fees (Explicitly)
        delivery_match = re.search(r'-\s+(?:Delivery|Handling).*?(\d+\.\d{2})\s*$', text, re.IGNORECASE | re.MULTILINE)
        if delivery_match:
            try:
                data.items.append({
                    'name': 'Delivery & Handling Charges',
                    'quantity': '1',
                    'cost': float(delivery_match.group(1))
                })
            except:
                pass

        # 5. Extract Total
        # Look for the final total at the bottom of the table or "Amount in Words"
        total_match = re.search(r'Total\s+[\d\.]+\s+[\d\.]+\s+([\d,]+\.\d{2})', text, re.IGNORECASE)
        if total_match:
            data.total_amount = float(total_match.group(1).replace(',', ''))
            # Safety check if total match failed to grab the bottom total line and grabbed an intermediate 'Total'
            if data.items and data.total_amount < sum(item['cost'] for item in data.items) * 0.9:
                data.total_amount = sum(item['cost'] for item in data.items)
        else:
            # Fallback: sum items
            if data.items:
                data.total_amount = sum(item['cost'] for item in data.items)

        return data

class GenericParser(BaseParser):
    def parse(self, text):
        data = ReceiptData(shop_name='Smart Scan')
        lines = text.split('\n')
        
        # 1. Date Detection
        date_pattern = re.compile(r'(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})')
        dates = date_pattern.findall(text)
        if dates: data.bill_date = dates[0]

        # 2. Number extraction - flexible patterns
        # Patterns: 123.45, 123. 45, 123 ,45, 123-45
        price_pattern = re.compile(r'(\d{1,6}[\s\.,-]+\d{2})(?!\d)')
        
        all_prices = []
        potential_items = []

        for line in lines:
            line = line.strip()
            if not line or len(line) < 5: continue
            
            # Look for numbers
            line_prices_raw = price_pattern.findall(line)
            if not line_prices_raw:
                # Try finding any integer > 10 at the end of the line
                int_match = re.search(r'(\d{2,6})$', line)
                if int_match:
                    line_prices_raw = [int_match.group(1)]
                else:
                    continue
            
            # Normalize prices
            floats = []
            for p in line_prices_raw:
                try:
                    # Remove spaces, replace , with .
                    clean_p = re.sub(r'[\s-]', '', p).replace(',', '.')
                    if '.' not in clean_p: # It was an integer from the fallback
                        val = float(clean_p)
                    else:
                        val = float(clean_p)
                    floats.append(val)
                except: continue
            
            if not floats: continue
            all_prices.extend(floats)
            
            # Item detection
            name_part = line
            for p_str in line_prices_raw:
                name_part = name_part.replace(p_str, '')
            
            clean_name = re.sub(r'^[0-9\.\s\-]+', '', name_part).strip()
            # Clean up middle junk
            clean_name = re.sub(r'\s{2,}', ' ', clean_name)
            
            if len(clean_name) > 3 and not any(kw in clean_name.upper() for kw in ['TOTAL', 'TAX', 'GST', 'CGST', 'SGST', 'VAT', 'CESS', 'AMOUNT', 'DATE', 'INVOICE', 'PAGE', 'TEL', 'FSSAI']):
                potential_items.append({
                    'name': clean_name,
                    'quantity': '1',
                    'cost': floats[-1]
                })

        # 3. Total Detection - Largest number usually
        if all_prices:
            data.total_amount = max(all_prices)
        
        # 4. Refine Items
        data.items = [it for it in potential_items if it['cost'] < data.total_amount * 0.95 or len(potential_items) == 1]
        
        # Fallback for Total
        if (not data.total_amount or data.total_amount < 1) and data.items:
            data.total_amount = sum(it['cost'] for it in data.items)

        return data
