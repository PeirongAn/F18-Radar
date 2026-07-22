from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from lxml import etree


SOURCE = Path(r"D:\codes\F18-Radar\.codex_tmp\trust_dev_doc\reference-fixed.docx")
OUTPUT = Path(r"D:\codes\F18-Radar\.codex_tmp\trust_dev_doc\reference-clean.docx")
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


with ZipFile(SOURCE, "r") as source:
    rels = etree.fromstring(source.read("word/_rels/document.xml.rels"))
    removed_ids = set()
    for rel in list(rels):
        if rel.get("Target") in {"../NULL", "NULL"}:
            removed_ids.add(rel.get("Id"))
            rels.remove(rel)

    document = etree.fromstring(source.read("word/document.xml"))
    ns = {"w": W_NS, "r": R_NS, "a": A_NS}
    for rel_id in removed_ids:
        for blip in document.xpath(f".//a:blip[@r:embed='{rel_id}']", namespaces=ns):
            drawing = blip
            while drawing is not None and drawing.tag != f"{{{W_NS}}}drawing":
                drawing = drawing.getparent()
            if drawing is not None and drawing.getparent() is not None:
                drawing.getparent().remove(drawing)

    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename == "word/_rels/document.xml.rels":
                data = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif item.filename == "word/document.xml":
                data = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)
            else:
                data = source.read(item.filename)
            target.writestr(item, data)

print(OUTPUT)
