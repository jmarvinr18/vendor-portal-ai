"""Tools that create a file for the vendor.

Each one writes to REPORTS_BUCKET under reports/<sessionId>/ and hands the portal a pointer
to it as the tool's artifact ({"name", "bucket", "key", "size"}). streaming.py forwards that
as an `artifact` event; vendor-portal-api checks it against its allowlist and serves the
download itself, so no presigned URL is created and the bucket stays private.
"""

import io
import os, re, uuid, boto3
from fpdf import FPDF
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from dotenv import load_dotenv
from config import load_secrets

load_dotenv()
load_secrets()

s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-southeast-1"))

TEXT_FORMATS = {"md": "text/markdown", "csv": "text/csv", "txt": "text/plain"}


def _latin1(text: str) -> str:
    repl = {"‘": "'", "’": "'", "“": '"', "”": '"',
            "–": "-", "—": "-", "•": "-", "…": "..."}
    for k, v in repl.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def _file_name(title: str, extension: str) -> str:
    """The vendor's download name: the title without characters file systems reject."""
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f\s]+', " ", title).strip(" .")[:100] or "report"
    return f"{stem}.{extension}"


def _store(body: bytes, name: str, extension: str, content_type: str, config: RunnableConfig):
    """Uploads the file for this conversation. Returns (message for the model, artifact)."""
    bucket = os.getenv("REPORTS_BUCKET")
    if not bucket:
        return f"{name} could not be created: REPORTS_BUCKET is not configured.", None
    session_id = (config.get("configurable") or {}).get("thread_id")
    if not session_id:
        return f"{name} could not be created: there is no conversation to attach it to.", None

    key = f"reports/{session_id}/{uuid.uuid4().hex}.{extension}"
    try:
        s3.upload_fileobj(io.BytesIO(body), bucket, key, ExtraArgs={"ContentType": content_type})
    except Exception as e:
        # Goes to the runtime's CloudWatch log; the model only gets a short message
        print(f"Creating {name} failed (bucket={bucket}, key={key}): {e!r}")
        return f"{name} could not be created because of a storage error. Please try again later.", None

    # The portal shows the download under the answer, so the model must not invent a link.
    message = (
        f"Created {name}. It is attached to your reply as a download; "
        "do not include a link or URL for it."
    )
    return message, {"name": name, "bucket": bucket, "key": key, "size": len(body)}


@tool(parse_docstring=True, response_format="content_and_artifact")
def create_pdf_report(title: str, content: str, config: RunnableConfig):
    """Create a PDF report the user can download. Use this whenever the user asks to export, save, or download something as a PDF.

    Args:
        title: The report title shown at the top of the first page.
        content: The full report body as plain text. Separate paragraphs with newlines.
    """
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

    # fpdf 1.7 returns the document as a latin-1 str, fpdf2 as a bytearray.
    out = pdf.output(dest="S")
    body = out.encode("latin-1") if isinstance(out, str) else bytes(out)
    return _store(body, _file_name(title, "pdf"), "pdf", "application/pdf", config)


@tool(parse_docstring=True, response_format="content_and_artifact")
def create_text_file(title: str, content: str, format: str, config: RunnableConfig):
    """Create a Markdown, CSV or plain-text file the user can download. Use CSV for tables the user wants to open in Excel, Markdown for formatted notes or summaries.

    Args:
        title: The file name, without an extension.
        content: The whole file. For CSV, a header row then one row per line, comma-separated.
        format: One of "md", "csv" or "txt".
    """
    extension = (format or "").lower().lstrip(".")
    if extension not in TEXT_FORMATS:
        return f'Unsupported format "{format}". Use md, csv or txt.', None
    # A BOM so Excel opens a CSV as UTF-8.
    body = ("﻿" if extension == "csv" else "") + content
    return _store(
        body.encode("utf-8"), _file_name(title, extension), extension,
        f"{TEXT_FORMATS[extension]}; charset=utf-8", config,
    )
