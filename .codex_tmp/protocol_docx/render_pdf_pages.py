from pathlib import Path

import pypdfium2 as pdfium


pdf_path = Path(
    r"D:\codes\F18-Radar\.codex_tmp\protocol_docx\rendered_web_update_v3"
    r"\external_task_behavior_pose_protocol_v1.0.pdf"
)
output_dir = pdf_path.parent

document = pdfium.PdfDocument(pdf_path)
for page_number, page in enumerate(document, start=1):
    bitmap = page.render(scale=2)
    bitmap.to_pil().save(output_dir / f"page-{page_number}.png")

print(f"rendered_pages={len(document)}")
