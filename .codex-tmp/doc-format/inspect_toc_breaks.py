import sys
from docx import Document
from docx.oxml.ns import qn


doc = Document(sys.argv[1])
for i, p in enumerate(doc.paragraphs[:48]):
    breaks = []
    for el in p._p.iter():
        if el.tag in {qn("w:br"), qn("w:lastRenderedPageBreak"), qn("w:pageBreakBefore")}:
            breaks.append((el.tag.split("}")[-1], dict(el.attrib)))
    if breaks:
        print(i, repr(p.text), breaks)
