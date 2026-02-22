import json
import os
import shutil
import platform
import subprocess
import fitz
import io
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

def load_company_history() -> List[str]:
    """Načte historii firem z lokálního souboru."""
    history_file = Path("companies.json")
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_company_to_history(name: str):
    """Uloží firmu do historie (na začátek, bez duplicit)."""
    if not name or name == "moje_firma":
        return
    history = load_company_history()
    if name in history:
        history.remove(name)
    history.insert(0, name)
    history = history[:20]
    try:
        with open("companies.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except:
        pass

def find_naps2() -> Optional[str]:
    """Pokusí se najít NAPS2.Console.exe."""
    path_found = shutil.which("NAPS2.Console.exe")
    if path_found:
        return path_found
        
    common_paths = [
        r"C:\Program Files\NAPS2\NAPS2.Console.exe",
        r"C:\Program Files (x86)\NAPS2\NAPS2.Console.exe",
        str(Path.home() / "AppData" / "Local" / "NAPS2" / "NAPS2.Console.exe")
    ]
    
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None

def run_naps2_scan(company_name: str) -> List[Dict[str, Any]]:
    """Spustí NAPS2 scan."""
    if platform.system() != "Windows":
        return []
    
    naps2_path = find_naps2()
    if not naps2_path:
        return []

    safe_company = "".join([c for c in company_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scan_dir = Path("scans") / safe_company / timestamp
    scan_dir.mkdir(parents=True, exist_ok=True)
    
    output_pattern = str(scan_dir / "img-$(n).jpg")
    cmd = [naps2_path, "-p", "flexibee", "-o", output_pattern, "--split", "--progress"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        
        scanned_items = []
        files = sorted(list(scan_dir.glob("img-*.jpg")))
        for f_path in files:
            with open(f_path, "rb") as f:
                content = f.read()
                scanned_items.append({
                    "name": f_path.name,
                    "content": content,
                    "type": "image/jpeg"
                })
        return scanned_items
    except Exception:
        return []

def pdf_to_images(pdf_name: str, pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """Převede PDF na seznam obrázků."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY)
            img_bytes = pix.tobytes("jpg", jpg_quality=85)
            pages.append({
                "name": f"{pdf_name}_strana_{i+1}.jpg",
                "content": img_bytes,
                "type": "image/jpeg"
            })
        doc.close()
        return pages
    except Exception:
        return []
