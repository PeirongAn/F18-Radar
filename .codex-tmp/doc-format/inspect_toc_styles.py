import sys
from docx import Document


doc = Document(sys.argv[1])
for name in ("Normal", "toc 1", "toc 2", "toc 3", "TOC 1", "TOC 2", "TOC 3"):
    try:
        style = doc.styles[name]
    except KeyError:
        continue
    pf = style.paragraph_format
    font = style.font
    print(
        name,
        "size=", font.size.pt if font.size else None,
        "before=", pf.space_before.pt if pf.space_before else None,
        "after=", pf.space_after.pt if pf.space_after else None,
        "line=", pf.line_spacing,
        "keep_next=", pf.keep_with_next,
        "keep_lines=", pf.keep_together,
        "page_break=", pf.page_break_before,
        "widow=", pf.widow_control,
        "left=", pf.left_indent.pt if pf.left_indent else None,
        "first=", pf.first_line_indent.pt if pf.first_line_indent else None,
    )
