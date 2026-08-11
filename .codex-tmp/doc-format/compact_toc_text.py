from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


SOURCE = Path(r"D:\codes\F18-Radar\专题1-1典型智能KZ任务场景特征分析研究报告V8.docx")
OUTPUT = Path(r"D:\codes\F18-Radar\.codex-tmp\doc-format\专题1-1典型智能KZ任务场景特征分析研究报告V8_目录压缩.docx")


def set_half_points(rpr, value: str) -> None:
    for tag in ("w:sz", "w:szCs"):
        element = rpr.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            rpr.append(element)
        element.set(qn("w:val"), value)


doc = Document(SOURCE)
toc_styles = {"toc 1", "toc 2", "toc 3"}
changed = 0

for paragraph in doc.paragraphs:
    style_name = paragraph.style.name.lower() if paragraph.style else ""
    if style_name not in toc_styles:
        continue

    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0

    ppr = paragraph._p.get_or_add_pPr()
    snap_to_grid = ppr.find(qn("w:snapToGrid"))
    if snap_to_grid is None:
        snap_to_grid = OxmlElement("w:snapToGrid")
        ppr.append(snap_to_grid)
    snap_to_grid.set(qn("w:val"), "0")

    p_rpr = ppr.find(qn("w:rPr"))
    if p_rpr is None:
        p_rpr = OxmlElement("w:rPr")
        ppr.append(p_rpr)
    set_half_points(p_rpr, "20")

    for run_element in paragraph._p.iter(qn("w:r")):
        rpr = run_element.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            run_element.insert(0, rpr)
        set_half_points(rpr, "20")

    changed += 1

for style_name in ("toc 1", "toc 2", "toc 3"):
    try:
        doc.styles[style_name].font.size = Pt(10)
    except KeyError:
        pass

doc.save(OUTPUT)
print(f"saved={OUTPUT}")
print(f"toc_paragraphs_compacted={changed}")
