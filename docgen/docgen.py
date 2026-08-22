from docx import Document
import os

def generate_word_report(content: str, filename: str = "AI_Report.docx") -> str:
    """Takes extracted points and formats them into a Word document."""
    doc = Document()
    doc.add_heading('Agentic AI Analysis Report', 0)
    
    # Simple parsing: split by newlines and add as paragraphs/bullets
    for line in content.split('\n'):
        if line.strip():
            if line.strip().startswith(('-', '*')):
                doc.add_paragraph(line.strip()[1:].strip(), style='List Bullet')
            else:
                doc.add_paragraph(line.strip())
                
    doc.save(filename)
    filepath = os.path.abspath(filename)
    return f"Success: Report generated and saved locally at {filepath}"