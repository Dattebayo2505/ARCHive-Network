import os
import sys
from PIL import Image
from collections import defaultdict
import math

def gcd(a, b):
    if b == 0:
        return a
    return gcd(b, a % b)

def get_aspect_ratio(width, height):
    # common exact ratios
    common = {
        (16, 9): "16:9",
        (9, 16): "9:16",
        (4, 3): "4:3",
        (3, 4): "3:4",
        (3, 2): "3:2",
        (2, 3): "2:3",
        (1, 1): "1:1",
    }
    
    # Try to simplify exactly
    divisor = gcd(width, height)
    w_simp = width // divisor
    h_simp = height // divisor
    
    if (w_simp, h_simp) in common:
        return common[(w_simp, h_simp)]
        
    # Check for near matches due to slight cropping
    ratio = width / height
    
    for (w, h), name in common.items():
        if abs(ratio - (w / h)) < 0.05:
            return f"~{name}"
            
    return f"{w_simp}:{h_simp} ({width}x{height})"

def scan_dir(path):
    ratios = defaultdict(int)
    total = 0
    errors = 0
    
    for root, _, files in os.walk(path):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                try:
                    p = os.path.join(root, f)
                    with Image.open(p) as img:
                        w, h = img.size
                        ratio_str = get_aspect_ratio(w, h)
                        ratios[ratio_str] += 1
                        total += 1
                except Exception as e:
                    errors += 1
                    
    return ratios, total, errors

if __name__ == "__main__":
    scan_paths = ['workspace/ready', 'workspace/import', 'workspace/imports']
    
    for sp in scan_paths:
        if os.path.exists(sp):
            print(f"Scanning {sp}...")
            ratios, total, errors = scan_dir(sp)
            if total == 0:
                print("  No images found.")
                continue
                
            print(f"  Total images: {total}")
            print(f"  Errors reading images: {errors}")
            print("  Aspect Ratios:")
            
            # Sort by frequency
            sorted_ratios = sorted(ratios.items(), key=lambda x: x[1], reverse=True)
            for ratio, count in sorted_ratios:
                print(f"    - {ratio}: {count} images ({count/total*100:.1f}%)")
            print()
