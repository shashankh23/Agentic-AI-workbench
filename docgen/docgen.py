import os
import datetime
from docx import Document
from docx.shared import Pt, RGBColor

def generate_word_report(
    content: str, 
    filename: str = "AI_Report.docx", 
    source_name: str = "Direct User Input",
    ledger_hash: str = "N/A"
) -> str:
    """
    Generates a structured Word (.docx) document with a 
    cryptographic provenance audit block at the bottom.
    """
    doc = Document()
    
    # Title & Generation Metadata
    doc.add_heading('Sovereign AI Workbench Report', 0)
    sub = doc.add_paragraph(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Air-Gapped Host)")
    sub.runs[0].font.italic = True
    sub.runs[0].font.color.rgb = RGBColor(120, 120, 120)

    # Core Extracted Content
    doc.add_heading('Key Findings & Analysis', level=1)
    for line in content.split('\n'):
        clean_line = line.strip()
        if clean_line:
            if clean_line.startswith(('-', '*')):
                doc.add_paragraph(clean_line[1:].strip(), style='List Bullet')
            else:
                doc.add_paragraph(clean_line)

    # Document-Level Provenance Table
    doc.add_heading('Document Provenance & Audit Metadata', level=2)
    prov_table = doc.add_table(rows=3, cols=2)
    prov_table.style = 'Light Shading Accent 1'
    
    metadata = [
        ("Source Asset", os.path.basename(source_name)),
        ("Execution Host", "On-Premise 8GB Edge Workstation"),
        ("SHA-256 Ledger Hash", ledger_hash)
    ]
    
    for i, (key, value) in enumerate(metadata):
        prov_table.rows[i].cells[0].text = key
        prov_table.rows[i].cells[1].text = value

    doc.save(filename)
    return os.path.abspath(filename)