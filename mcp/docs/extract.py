"""Turns a document file into text: PDF, Word (.docx), OpenDocument (.odt .ods .odp), Excel (.xlsx), PowerPoint (.pptx), HTML, text, Markdown, CSV.
extract(path) -> {"ok": True, "sections": [text, ...], "unit": "page"|"slide"|"sheet"|"document", "format": ext, "truncated": bool}
              or {"ok": False, "error": "what to tell the user"}.  It never raises: a damaged or unsupported file is an error message, not a crash."""
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

MAX_CHARS = int(os.environ.get("ROYVA_DOCS_MAX_CHARS", "1000000"))      # everything past this is dropped and reported as truncated
MAX_BYTES = int(os.environ.get("ROYVA_DOCS_MAX_BYTES", str(50 * 1024 * 1024)))
MAX_UNZIPPED = 200 * 1024 * 1024                                         # a small zip that unpacks to this much is refused (zip bomb)
TEXT = {".txt", ".md", ".markdown", ".log", ".json", ".yaml", ".yml", ".xml", ".rtf"}
UNSUPPORTED = {".doc": "Old .doc files cannot be read here. Please send it again as .docx, .odt or PDF.",
               ".xls": "Old .xls files cannot be read here. Please send it again as .xlsx, .ods or CSV.",
               ".ppt": "Old .ppt files cannot be read here. Please send it again as .pptx, .odp or PDF."}


def _fail(msg): return {"ok": False, "error": msg}


def _ok(sections, unit, ext):
    out, used, cut = [], 0, False
    for s in sections:
        s = s.strip("\n")
        if used + len(s) > MAX_CHARS:
            out.append(s[:max(0, MAX_CHARS - used)]); cut = True; break
        out.append(s); used += len(s)
    return {"ok": True, "sections": out, "unit": unit, "format": ext.lstrip("."), "truncated": cut}


class _Html(HTMLParser):
    def __init__(self): super().__init__(); self.out, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"): self.skip += 1
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"): self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"): self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip: self.out.append(data)


def _text_file(path):
    raw = Path(path).read_bytes()[:MAX_CHARS * 4 + 4]
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try: return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError): continue
    return raw.decode("utf-8", "replace")


def _pdf(path):
    from pypdf import PdfReader
    r = PdfReader(path)
    if r.is_encrypted:
        try:
            if not r.decrypt(""): return _fail("This PDF is password protected, so it cannot be read.")
        except Exception: return _fail("This PDF is password protected, so it cannot be read.")
    pages = []
    for p in r.pages:
        try: pages.append((p.extract_text() or "").strip())
        except Exception: pages.append("")
    if not any(pages): return _fail("This PDF has no text in it (it looks like a scan or a picture). It cannot be read here.")
    return _ok(pages, "page", ".pdf")


def _docx(path):
    import docx
    d = docx.Document(path); parts = []
    def table(t):
        for row in t.rows:
            cells = []
            for c in row.cells:
                if c.text not in cells: cells.append(c.text)
            parts.append(" | ".join(x.strip() for x in cells))
    try:
        for item in d.iter_inner_content():
            if hasattr(item, "rows"): table(item)
            else: parts.append(item.text)
    except AttributeError:
        parts.extend(p.text for p in d.paragraphs)
        for t in d.tables: table(t)
    return _ok(["\n".join(parts)], "document", ".docx")


def _xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True); out = []
    for ws in wb.worksheets:
        rows = ["\t".join("" if v is None else str(v) for v in row).rstrip() for row in ws.iter_rows(values_only=True)]
        out.append(f"Sheet: {ws.title}\n" + "\n".join(r for r in rows if r))
    return _ok(out, "sheet", ".xlsx")


def _pptx(path):
    import pptx
    out = []
    for slide in pptx.Presentation(path).slides:
        lines = []
        for sh in slide.shapes:
            if sh.has_text_frame: lines.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows: lines.append(" | ".join(c.text for c in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None: lines.append("Notes: " + slide.notes_slide.notes_text_frame.text)
        out.append("\n".join(x for x in lines if x.strip()))
    return _ok(out, "slide", ".pptx")


def _local(el): return el.tag.rsplit("}", 1)[-1]


def _odf_text(el):
    """Visible text of an OpenDocument element, keeping paragraph breaks and table rows."""
    name = _local(el)
    if name in ("p", "h"):
        return "".join(_inline(el)) + "\n"
    if name == "table-row":
        cells = ["".join(_odf_text(c)).strip() for c in el if _local(c) in ("table-cell", "covered-table-cell")]
        return " | ".join(cells) + "\n"
    return "".join(_odf_text(c) for c in el)


def _inline(el):
    if el.text: yield el.text
    for c in el:
        n = _local(c)
        if n == "s": yield " "
        elif n == "tab": yield "\t"
        elif n == "line-break": yield "\n"
        else: yield from _inline(c)
        if c.tail: yield c.tail


def _odf(path, ext):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED: return _fail("This file is too large to open.")
        root = ET.fromstring(z.read("content.xml"))
    body = next((c for c in root.iter() if _local(c) in ("text", "spreadsheet", "presentation") and _local(c) != "document-content"), root)
    if ext == ".ods":
        return _ok([f"Sheet: {t.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name', '')}\n" + _odf_text(t) for t in body.iter() if _local(t) == "table"], "sheet", ext)
    if ext == ".odp":
        return _ok([_odf_text(pg) for pg in body.iter() if _local(pg) == "page"], "slide", ext)
    return _ok([_odf_text(body)], "document", ext)


def extract(path):
    p = Path(path); ext = p.suffix.lower()
    try:
        if ext in UNSUPPORTED: return _fail(UNSUPPORTED[ext])
        if ext not in TEXT | {".csv", ".html", ".htm", ".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}:
            return _fail(f"Files of type {ext or '(no extension)'} cannot be read here. Supported: PDF, .docx, .odt, .xlsx, .ods, .pptx, .odp, HTML, TXT, MD, CSV.")
        if p.stat().st_size > MAX_BYTES: return _fail("This file is too large to read (the limit is 50 MB).")
        if ext == ".pdf": return _pdf(str(p))
        if ext == ".docx": return _docx(str(p))
        if ext == ".xlsx": return _xlsx(str(p))
        if ext == ".pptx": return _pptx(str(p))
        if ext in (".odt", ".ods", ".odp"): return _odf(str(p), ext)
        text = _text_file(p)
        if ext in (".html", ".htm"):
            h = _Html(); h.feed(text); text = re.sub(r"\n\s*\n+", "\n", "".join(h.out))
        return _ok([text], "document", ext)
    except Exception as e:                                       # a damaged file is a message for the user, not a crash
        return _fail(f"This {ext.lstrip('.').upper() or 'file'} could not be opened ({type(e).__name__}); it may be damaged or protected.")
