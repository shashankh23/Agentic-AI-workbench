import pdfplumber

def extract_tables_from_pdf(pdf_path: str) -> list:
    """
    Extracts tables from a text-based PDF, returns list of markdown-formatted tables.
    """
    markdown_tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                md = _table_to_markdown(table)
                markdown_tables.append(f"**Table (page {page_num + 1}):**\n{md}")
    return markdown_tables

def _table_to_markdown(table: list) -> str:
    """Converts a list-of-lists table into a markdown grid."""
    rows = [[cell if cell is not None else "" for cell in row] for row in table]
    header = rows[0]
    body = rows[1:]

    md_lines = []
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in body:
        md_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(md_lines)
