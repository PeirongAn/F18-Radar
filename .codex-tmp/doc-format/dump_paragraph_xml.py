import sys
from docx import Document

doc = Document(sys.argv[1])
for raw in sys.argv[2:]:
    i = int(raw)
    p = doc.paragraphs[i]
    print(f"PARAGRAPH {i}: {p.text}")
    print(p._p.xml)
