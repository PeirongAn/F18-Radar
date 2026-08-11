from __future__ import annotations

import posixpath
import sys
import zipfile
from collections import Counter
from pathlib import PurePosixPath

from lxml import etree


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def source_for_rels(name):
    p = PurePosixPath(name)
    if p.name == ".rels" and str(p.parent) == "_rels":
        return ""
    if p.parent.name != "_rels" or not p.name.endswith(".rels"):
        return None
    return str(p.parent.parent / p.name[:-5])


def main(path):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        print("members", len(names))
        for name in sorted(names):
            if name.endswith((".xml", ".rels")):
                try:
                    etree.fromstring(z.read(name))
                except Exception as exc:
                    print("XML_ERROR", name, exc)
        for name in sorted(n for n in names if n.endswith(".rels")):
            root = etree.fromstring(z.read(name))
            rels = root.findall(f"{{{REL_NS}}}Relationship")
            print("RELS", name)
            for rel in rels:
                print(" ", rel.get("Id"), rel.get("Type"), rel.get("Target"), rel.get("TargetMode"))
            ids = [r.get("Id") for r in rels]
            dupes = [i for i, c in Counter(ids).items() if c > 1]
            if dupes:
                print("DUP_IDS", name, dupes)
            source = source_for_rels(name)
            base = posixpath.dirname(source or "")
            for r in rels:
                target = r.get("Target")
                mode = r.get("TargetMode")
                if not target:
                    print("EMPTY_TARGET", name, r.get("Id"), r.get("Type"))
                    continue
                if mode != "External":
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved.startswith("/"):
                        resolved = resolved[1:]
                    if resolved not in names:
                        print("MISSING_TARGET", name, r.get("Id"), target, "=>", resolved, r.get("Type"))
                elif mode not in {"External", None}:
                    print("BAD_MODE", name, r.get("Id"), mode)

        for name in sorted(n for n in names if n.endswith(".xml") and not n.endswith(".rels")):
            p = PurePosixPath(name)
            rels_name = str(p.parent / "_rels" / f"{p.name}.rels")
            ids = set()
            if rels_name in names:
                rel_root = etree.fromstring(z.read(rels_name))
                ids = {r.get("Id") for r in rel_root.findall(f"{{{REL_NS}}}Relationship")}
            root = etree.fromstring(z.read(name))
            refs = []
            all_rid_refs = []
            for el in root.iter():
                for attr_name, value in el.attrib.items():
                    if isinstance(value, str) and value.startswith("rId"):
                        all_rid_refs.append((el.tag, attr_name, value))
                    if attr_name.startswith(f"{{{OFFICE_REL_NS}}}"):
                        refs.append((el.tag, attr_name, value))
            for tag, attr_name, value in refs:
                if value not in ids:
                    print("MISSING_REL_ID", name, value, tag, attr_name, "rels=", rels_name)
            if name == "word/document.xml":
                print("DOCUMENT_REL_REFS", sorted({value for _, _, value in refs}))
                print("DOCUMENT_ALL_RID_REFS", sorted({value for _, _, value in all_rid_refs}))


if __name__ == "__main__":
    main(sys.argv[1])
