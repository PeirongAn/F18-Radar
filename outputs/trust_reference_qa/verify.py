import pypdfium2 as pdfium
from pathlib import Path
from docx import Document
p=Path(r'D:\codes\F18-Radar\outputs\trust_reference_qa')
d=pdfium.PdfDocument(str(p/'preview.pdf'))
print('Pages:',len(d))
for i in range(len(d)):
 page=d[i]; page.render(scale=1.5).to_pil().save(p/f'page-{i+1}.png')
 print(i+1, page.get_textpage().get_text_range()[-80:])
x=Document(r'D:\codes\F18-Radar\outputs\人机信任调控因素及试验设计参考.docx')
print('Normal font',x.styles['Normal'].font.name,x.styles['Normal'].font.size.pt)
print('Indent',x.styles['Normal'].paragraph_format.first_line_indent.pt)
