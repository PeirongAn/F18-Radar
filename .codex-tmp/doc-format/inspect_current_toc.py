import sys

from docx import Document


doc = Document(sys.argv[1])
for index, paragraph in enumerate(doc.paragraphs):
    style_name = paragraph.style.name.lower() if paragraph.style else ""
    if style_name in {"toc 1", "toc 2", "toc 3"}:
        print(index, style_name, repr(paragraph.text))
        print(paragraph._p.pPr.xml)
        if paragraph.runs:
            print(paragraph.runs[0]._r.xml)
        break
