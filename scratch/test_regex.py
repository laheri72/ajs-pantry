import sys
import re

text = """
     1. 04015000 1 Amul Fresh Cream -250ml                 1.0    68.00    68.00  
     2. 19053100 2 Britannia Milk Bikis Biscuits 710Gm     1.0    73.00    73.00  
"""

old_item_pattern = re.compile(r'^\s*(\d+)\.\s+(\d{4,10})\s+(\d+)\s+(.*?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)', re.MULTILINE)
matches = old_item_pattern.findall(text)
for m in matches:
    print(m)
