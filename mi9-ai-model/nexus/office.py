"""Office document text extraction — docx / pptx / xlsx — using only the stdlib.

These formats are ZIP archives of XML, so no external parser is needed (PDF is a
real parser and is intentionally skipped here). `extract(path)` returns plain text.
"""
import re
import zipfile


def _texts(xml_bytes, tag):
    """Pull the text out of <w:t> (Word) / <a:t> (Drawing) elements."""
    pat = re.compile(rb"<%s[^>]*>(.*?)</%s>" % (tag, tag), re.S)
    parts = [m.group(1).decode("utf-8", "ignore") for m in pat.finditer(xml_bytes)]
    return " ".join(p for p in parts if p.strip())


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    return _texts(xml, b"w:t")


def pptx_text(path):
    with zipfile.ZipFile(path) as z:
        slides = sorted(
            (n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
            key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        out = []
        for i, s in enumerate(slides, 1):
            body = _texts(z.read(s), b"a:t")
            out.append(f"[slide {i}]\n{body}")
        return "\n\n".join(out)


def xlsx_text(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = z.read("xl/sharedStrings.xml")
            shared = [m.group(1).decode("utf-8", "ignore")
                      for m in re.finditer(rb"<t[^>]*>(.*?)</t>", ss, re.S)]
        sheets = sorted(n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        out = []
        for s in sheets:
            xml = z.read(s)
            cells = re.findall(rb'<c[^>]*?(?:\s+t="(\w+)")?[^>]*>(?:<v>(.*?)</v>)?',
                               xml, re.S)
            vals = []
            for t, v in cells:
                if not v:
                    continue
                txt = v.decode("utf-8", "ignore")
                if t == b"s" and txt.isdigit() and int(txt) < len(shared):
                    txt = shared[int(txt)]
                vals.append(txt)
            out.append(f"[{s}]\n" + " | ".join(vals))
        return "\n\n".join(out)


def extract(path, max_chars=20000):
    """Extract text from a docx/pptx/xlsx file. Returns '' if unsupported."""
    p = str(path).lower()
    try:
        if p.endswith(".docx"):
            return docx_text(path)[:max_chars]
        if p.endswith(".pptx"):
            return pptx_text(path)[:max_chars]
        if p.endswith(".xlsx"):
            return xlsx_text(path)[:max_chars]
    except Exception as e:
        return f"[office extract error: {type(e).__name__}: {e}]"
    return ""