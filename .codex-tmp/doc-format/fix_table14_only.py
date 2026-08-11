import sys
from docx import Document

from repair_format import format_problem_table


doc = Document(sys.argv[1])
format_problem_table(doc.tables[14])
doc.save(sys.argv[2])
print(sys.argv[2])
