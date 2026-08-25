from pathlib import Path

from pypdf import PdfReader


for path in sorted(Path(r"C:\Users\hrush\Downloads").glob("czmp_*.pdf")):
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:3])
    print(f"\nFILE {path.name}\nPAGES {len(reader.pages)}\nENCRYPTED {reader.is_encrypted}\nMETADATA {dict(reader.metadata or {})}\nTEXT\n{text[:1800]}")
