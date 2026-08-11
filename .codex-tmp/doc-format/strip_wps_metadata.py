from __future__ import annotations

import sys
import zipfile
from pathlib import PurePosixPath

from lxml import etree


PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CUSTOM_XML_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
CUSTOM_PROPS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"


def main(src, dst):
    with zipfile.ZipFile(src, "r") as zin:
        content_types = etree.fromstring(zin.read("[Content_Types].xml"))
        for node in list(content_types):
            part = node.get("PartName", "")
            ctype = node.get("ContentType", "")
            if part.startswith("/customXml/") or part == "/docProps/custom.xml" or "custom-properties" in ctype or "customXml" in ctype:
                content_types.remove(node)

        root_rels = etree.fromstring(zin.read("_rels/.rels"))
        for rel in list(root_rels.findall(f"{{{PKG_REL_NS}}}Relationship")):
            if rel.get("Type") == CUSTOM_PROPS_REL or rel.get("Target") == "docProps/custom.xml":
                root_rels.remove(rel)

        doc_rels = etree.fromstring(zin.read("word/_rels/document.xml.rels"))
        for rel in list(doc_rels.findall(f"{{{PKG_REL_NS}}}Relationship")):
            if rel.get("Type") == CUSTOM_XML_REL or rel.get("Target", "").startswith("../customXml/"):
                doc_rels.remove(rel)

        replacements = {
            "[Content_Types].xml": etree.tostring(content_types, xml_declaration=True, encoding="UTF-8", standalone=True),
            "_rels/.rels": etree.tostring(root_rels, xml_declaration=True, encoding="UTF-8", standalone=True),
            "word/_rels/document.xml.rels": etree.tostring(doc_rels, xml_declaration=True, encoding="UTF-8", standalone=True),
        }

        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                name = info.filename
                if name.startswith("customXml/") or name == "docProps/custom.xml":
                    continue
                data = replacements.get(name, zin.read(name))
                zout.writestr(info, data)
    print(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
