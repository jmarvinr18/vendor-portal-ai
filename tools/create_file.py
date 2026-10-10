import os, uuid, boto3
from fpdf import FPDF
from langchain_core.tools import tool

S3_BUCKET = os.environ["REPORTS_BUCKET"]
s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-southeast-1"))

def _latin1(text: str) -> str:
    repl = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2013": "-", "\u2014": "-", "\u2022": "-", "\u2026": "..."}
    for k, v in repl.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")

@tool(parse_docstring=True)
def create_pdf_report(title: str, content: str) -> str:
    """Create a PDF report and return a download link. Use this whenever the user asks to export, save, or download something as a PDF.

    Args:
        title: The report title shown at the top of the first page.
        content: The full report body as plain text. Separate paragraphs with newlines.
    """
    path = f"/tmp/{uuid.uuid4().hex}.pdf"
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=20)
    pdf.multi_cell(0, 15, _latin1(title), align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", size=12)
    for para in content.split("\n"):
        if para.strip():
            pdf.multi_cell(0, 7, _latin1(para.strip()))
            pdf.ln(4)
    pdf.output(path)

    key = f"reports/{os.path.basename(path)}"
    s3.upload_file(path, S3_BUCKET, key, ExtraArgs={"ContentType": "application/pdf"})
    os.remove(path)
    url = s3.generate_presigned_url("get_object",
                                    Params={"Bucket": S3_BUCKET, "Key": key},
                                    ExpiresIn=3600)
    return f"PDF created. Download link (valid 1 hour): {url}"