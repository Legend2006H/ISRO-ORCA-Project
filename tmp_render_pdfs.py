from pathlib import Path

import fitz


output = Path("tmp_pdf_renders")
output.mkdir(exist_ok=True)
for path in sorted(Path(r"C:\Users\hrush\Downloads").glob("czmp_*.pdf")):
    document = fitz.open(path)
    pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    pixmap.save(output / f"{path.stem}.png")
